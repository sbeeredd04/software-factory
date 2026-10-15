"""Regenerate marketing PNGs with an explicitly prepared, offline developer toolchain."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.server
import json
import os
import re
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import uuid
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SIZES = {
    "social-preview": (1280, 640), "hero": (1600, 900),
    "loop": (1200, 800), "team": (1200, 800), "hosts": (1200, 800),
    "launch-landscape": (1200, 675), "launch-portrait": (1080, 1350),
}
FONTS = {
    "site/fonts/bricolage/BricolageGrotesque96pt-Bold.woff2": "908de7414bcad8649c2127a27e9aec08159059fca39b42bf724b4327a6780961",
    "site/fonts/inter/Inter-Regular.woff2": "e06f6b1bc553aaea4e4668023ed0ab0a147129c3107f511bc7d03d361b0ae085",
    "site/fonts/inter/Inter-SemiBold.woff2": "5cb7103e4e605989afebc03d989c79201e54b21b5183db33981f70db9178a301",
    "site/fonts/jetbrains-mono/JetBrainsMono-Regular.woff2": "a9cb1cd82332b23a47e3a1239d25d13c86d16c4220695e34b243effa999f45f2",
}
VERSIONS = {"playwright": "1.64.0", "greenlet": "3.5.6", "pyee": "14.0.0", "typing_extensions": "4.16.0"}
INPUTS = {
    "scripts/render_assets.py",
    "assets/toolchain.json", "assets/tools/capture.py", "assets/templates/assets.css",
    "assets/templates/ready.js", "site/styles/tokens.css", "site/styles/base.css",
    "site/img/mark.svg", *FONTS,
    *(f"assets/templates/{name}.html" for name in SIZES),
}
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "font-src 'self'; connect-src 'none'; object-src 'none'; frame-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
LIMIT = 24 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("invalid relative asset path")
    parts = PurePosixPath(name).parts
    if name != "/".join(parts) or any(p in (".", "..", "") for p in parts) or name.startswith("/"):
        raise ValueError("invalid relative asset path")
    return parts


@contextlib.contextmanager
def directory(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_at(root_fd, name, *, missing=False):
    return snapshot_at(root_fd, name, missing=missing)[0]


def snapshot_at(root_fd, name, *, missing=False):
    parts = relative(name)
    with directory(root_fd, parts[:-1]) as parent:
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            if missing:
                return None, None
            raise
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                raise ValueError("asset source/output must be a bounded regular file")
            data = stream.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError("asset exceeds byte limit")
            return data, (info.st_dev, info.st_ino)


def load_sources(root_fd):
    raw = read_at(root_fd, "assets/manifest.json")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or set(manifest) != {"version", "inputs", "assets"} or manifest["version"] != 1:
        raise ValueError("invalid asset manifest")
    if not isinstance(manifest["inputs"], list) or not all(isinstance(name, str) for name in manifest["inputs"]) or sorted(manifest["inputs"]) != sorted(INPUTS):
        raise ValueError("manifest must declare the exact public input allowlist")
    entries = manifest["assets"]
    if not isinstance(entries, list) or len(entries) != len(SIZES):
        raise ValueError("manifest must declare all seven assets")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "template", "output", "width", "height", "copies", "use"}:
            raise ValueError("invalid asset entry")
        name = entry["id"]
        if not isinstance(name, str) or name not in SIZES or name in seen:
            raise ValueError("unknown or duplicate asset")
        seen.add(name)
        copies = [f"site/img/{name}.png"] if name in ("loop", "team", "hosts") else []
        if (entry["template"] != f"assets/templates/{name}.html"
                or entry["output"] != f"assets/{name}.png" or entry["copies"] != copies
                or (entry["width"], entry["height"]) != SIZES[name]
                or not isinstance(entry["use"], str) or not entry["use"].strip()):
            raise ValueError("asset contract differs from the reviewed finite set")
    sources = {name: read_at(root_fd, name) for name in sorted(INPUTS)}
    sources["assets/manifest.json"] = raw
    toolchain = json.loads(sources["assets/toolchain.json"])
    if toolchain != {"version": 1, "packages": VERSIONS, "browser": "chromium-headless-shell",
                     "browser_version": "156.0.8078.4", "browser_revision": "1248"}:
        raise ValueError("toolchain differs from the reviewed pin")
    for name, expected in FONTS.items():
        if digest(sources[name]) != expected:
            raise ValueError("font source differs from its reviewed unmodified bytes")
    return manifest, sources


def png_size(data):
    """Validate PNG structure, CRCs and the bounded decompressed pixel stream."""
    if len(data) > LIMIT or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature or size")
    offset, size, compressed, ended, palette, data_closed = 8, None, bytearray(), False, False, False
    data_seen = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("truncated PNG chunk")
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if not kind.isalpha() or kind[2:3].islower():
            raise ValueError("invalid PNG chunk type")
        end = offset + length + 12
        if end > len(data) or length > LIMIT:
            raise ValueError("invalid PNG chunk length")
        payload = data[offset + 8:end - 4]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != struct.unpack(">I", data[end - 4:end])[0]:
            raise ValueError("PNG chunk CRC mismatch")
        if kind == b"IHDR":
            if offset != 8 or size is not None or length != 13:
                raise ValueError("invalid PNG header")
            width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if not (0 < width <= 2000 and 0 < height <= 2000) or (depth, comp, filt, interlace) != (8, 0, 0, 0) or color not in (2, 6):
                raise ValueError("unsupported PNG pixel layout")
            size, channels = (width, height), 3 if color == 2 else 4
        elif kind == b"PLTE":
            if not size or palette or data_seen or length == 0 or length > 768 or length % 3:
                raise ValueError("invalid PNG palette")
            palette = True
        elif kind == b"IDAT" and size:
            if data_closed:
                raise ValueError("nonconsecutive PNG image data")
            data_seen = True
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or end != len(data) or not compressed:
                raise ValueError("invalid PNG terminator")
            ended = True
        elif not size or kind[:1].isupper() and kind != b"PLTE":
            raise ValueError("unknown PNG critical chunk")
        elif data_seen:
            data_closed = True
        offset = end
    if not ended or size is None:
        raise ValueError("incomplete PNG")
    row = size[0] * channels + 1
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(bytes(compressed), row * size[1] + 1)
    if (len(pixels) != row * size[1] or not decoder.eof or decoder.unused_data
            or any(pixels[i] > 4 for i in range(0, len(pixels), row))):
        raise ValueError("invalid PNG pixel stream")
    return size


def launch_proof(log):
    launches = re.findall(r"<launching> ([^\n]+)", log)
    if len(launches) != 1:
        raise ValueError("missing or ambiguous actual browser launch proof")
    flags = re.findall(r"(?<!\S)(--[A-Za-z0-9-]+)(?:=\S+)?", launches[0])
    unsafe = {"--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security",
              "--disable-gpu-sandbox", "--single-process", "--no-zygote",
              "--enable-unsafe-swiftshader", "--allow-file-access-from-files",
              "--remote-debugging-port", "--proxy-server", "--proxy-bypass-list"}
    if unsafe.intersection(flags) or not {"--headless", "--user-data-dir", "--remote-debugging-pipe"} <= set(flags):
        raise ValueError("browser launch proof has unsafe or missing isolation flags")
    return {"flags": flags, "log_sha256": digest(log.encode()), "chromium_sandbox": True}


@contextlib.contextmanager
def serving(sources):
    public = {"/" + name: data for name, data in sources.items() if Path(name).suffix in MIME}
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlsplit(self.path)
            path = unquote(route.path)
            data = public.get(path) if not route.query and path == route.path else None
            status = 200 if data is not None else 404
            if len(requests) >= 300:
                data, status = None, 429
            if len(requests) <= 300:
                requests.append({"path": path[:200], "status": status})
            self.send_response(status)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Type", MIME.get(Path(path).suffix, "text/plain"))
            self.send_header("Content-Length", str(len(data) if data is not None else 0))
            self.end_headers()
            if data is not None:
                self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def developer_command(helper, job):
    return ["uvx", "--offline", "--python", sys.executable, "--from", "playwright==1.64.0",
            "--with", "greenlet==3.5.6", "--with", "pyee==14.0.0",
            "--with", "typing_extensions==4.16.0", "python", str(helper), "--job", str(job)]


def private_log(folder, name, value):
    """Retain bounded raw diagnostics only in the explicitly selected private run."""
    data = value.encode() if isinstance(value, str) else value or b""
    folder_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder_fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data[:2 * 1024 * 1024])
    finally:
        os.close(folder_fd)
    return len(data) <= 2 * 1024 * 1024


@contextlib.contextmanager
def termination_guard():
    """Turn SIGTERM into a handled interruption; restore the caller's disposition."""
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("asset rendering must run on the main thread for signal cleanup")
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(_signum, _frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        # InterruptedError is swallowed as EINTR by selectors used by communicate().
        raise RuntimeError("asset rendering interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def run_child(argv, env, evidence, *, timeout=300):
    with termination_guard():
        return child_process(argv, env, evidence, timeout=timeout)


def child_process(argv, env, evidence, *, timeout):
    process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    stdout, stderr = "", ""
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
        raise
    finally:
        complete_out = private_log(evidence, "capture-stdout.log", stdout)
        complete_err = private_log(evidence, "capture-stderr.log", stderr)
    if process.returncode:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        raise ValueError("developer browser helper failed; inspect the private capture log")
    if not complete_out or not complete_err:
        raise ValueError("developer capture exceeded the bounded diagnostic log size")
    if stdout.strip() != "asset capture complete":
        raise ValueError("unexpected developer helper response")
    return stderr


def validate_report(report, manifest):
    if (report.get("packages") != VERSIONS or report.get("browser_version") != "156.0.8078.4"
            or report.get("settings") != {"sandbox": True, "scale": 1, "locale": "en-US",
                                          "timezone": "UTC", "color_scheme": "light",
                                          "service_workers": "block", "permissions": []}):
        raise ValueError("unexpected observed toolchain or capture settings")
    captures = report.get("captures", [])
    if len(captures) != len(manifest["assets"]):
        raise ValueError("incomplete browser readiness report")
    for capture, entry in zip(captures, manifest["assets"], strict=True):
        ready = capture.get("ready", {})
        if (capture.get("id") != entry["id"] or capture.get("errors") != []
                or ready.get("viewport") != [entry["width"], entry["height"]]
                or ready.get("fonts") != ["Bricolage:700", "Inter:400", "Inter:600", "JetBrains Mono:400"]
                or ready.get("overflow") != [] or ready.get("failed") != []
                or ready.get("images_decoded") is not True
                or not capture.get("requests")):
            raise ValueError("browser readiness failed")


def capture(manifest, sources, stage, cache, evidence):
    helper = stage / "capture.py"
    helper.write_bytes(sources["assets/tools/capture.py"])
    env = dict(os.environ, UV_CACHE_DIR=str(cache / "uv"),
               PLAYWRIGHT_BROWSERS_PATH=str(cache / "browsers"),
               UV_PYTHON_DOWNLOADS="never", PLAYWRIGHT_SKIP_BROWSER_GC="1",
               DEBUG="pw:browser", TMPDIR=str(stage / "browser-tmp"))
    (stage / "browser-tmp").mkdir()
    with serving(sources) as (origin, requests):
        job = {"version": 1, "origin": origin, "assets": manifest["assets"]}
        job_path = stage / "job.json"
        job_path.write_bytes(encoded(job))
        log = run_child(developer_command(helper, job_path), env, evidence)
        proof = launch_proof(log)
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            report = json.loads(read_at(stage_fd, "browser-report.json"))
        finally:
            os.close(stage_fd)
        validate_report(report, manifest)
        if any(item["status"] != 200 for item in requests):
            raise ValueError("staged input request failed")
    outputs = {}
    for entry in manifest["assets"]:
        data = (stage / (entry["id"] + ".png")).read_bytes()
        if png_size(data) != (entry["width"], entry["height"]):
            raise ValueError("captured PNG dimensions differ from the manifest")
        for target in [entry["output"], *entry["copies"]]:
            outputs[target] = data
    return outputs, {"browser": report, "launch": proof, "server_requests": requests}


def visible_directories(root_fd, root_path, parents):
    """Refuse publication through descriptors detached from the visible checkout."""
    if root_path is not None:
        current = os.stat(root_path, follow_symlinks=False)
        held = os.fstat(root_fd)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise ValueError("visible checkout root changed during rendering")
    for name, held_fd in parents.items():
        with directory(root_fd, relative(name)) as current_fd:
            current, held = os.fstat(current_fd), os.fstat(held_fd)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError("visible asset parent changed during publication")


def publish(root_fd, outputs, root_path=None, recovery=None):
    """Prepare every target first; replace per file, rolling back handled failures."""
    expected = {f"assets/{name}.png" for name in SIZES} | {
        f"site/img/{name}.png" for name in ("loop", "team", "hosts")} | {"assets/render-receipt.json"}
    if set(outputs) != expected:
        raise ValueError("publication must include the complete output set and receipt")
    prepared, changed, retained = [], [], False
    with contextlib.ExitStack() as stack:
        parents = {name: stack.enter_context(directory(root_fd, (name,))) for name in ("assets",)}
        parents["site/img"] = stack.enter_context(directory(root_fd, ("site", "img")))
        visible_directories(root_fd, root_path, parents)

        def temporary(fd, data, item, key):
            name = ".sf-asset-" + uuid.uuid4().hex
            file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
            info = os.fstat(file_fd)
            item[key] = name
            item[key + "_snapshot"] = (data, (info.st_dev, info.st_ino))
            with os.fdopen(file_fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())

        def check_temporary(item, key, missing=False):
            if item[key] is None:
                return
            current = snapshot_at(item["fd"], item[key], missing=missing)
            if missing and current == (None, None):
                return
            if current != item[key + "_snapshot"]:
                raise ValueError("prepared asset temporary ownership is contested")

        def record_recovery():
            if recovery is not None:
                recovery({"version": 1, "status": "contested-or-failed-publication",
                          "files": [{"target": item["path"],
                                     "new": item["new"], "backup": item["old"],
                                     "expected_new_sha256": digest(item["after"][0]) if item["after"] else None,
                                     "expected_prior_sha256": digest(item["before"][0]) if item["before"][0] is not None else None}
                                    for item in prepared]})

        try:
            names = sorted(expected - {"assets/render-receipt.json"}) + ["assets/render-receipt.json"]
            for path in names:
                old, identity = snapshot_at(root_fd, path, missing=True)
                parent, name = path.rsplit("/", 1)
                fd = parents[parent]
                item = {"fd": fd, "name": name, "new": None, "old": None,
                        "before": (old, identity), "after": None, "path": path}
                prepared.append(item)
                temporary(fd, outputs[path], item, "new")
                item["after"] = item["new_snapshot"]
                if old is not None:
                    temporary(fd, old, item, "old")
            for item in prepared:
                check_temporary(item, "new")
                check_temporary(item, "old")
            for item in prepared:
                visible_directories(root_fd, root_path, parents)
                check_temporary(item, "new")
                check_temporary(item, "old")
                if snapshot_at(item["fd"], item["name"], missing=True) != item["before"]:
                    raise ValueError("asset changed during publication preparation")
                changed.append(item)
                os.replace(item["new"], item["name"], src_dir_fd=item["fd"], dst_dir_fd=item["fd"])
            for fd in parents.values():
                os.fsync(fd)
            visible_directories(root_fd, root_path, parents)
            for item in prepared:
                if snapshot_at(item["fd"], item["name"], missing=True) != item["after"]:
                    raise ValueError("published asset changed before final verification")
        except BaseException as original:
            rollback_errors = []
            for item in reversed(changed):
                try:
                    visible_directories(root_fd, root_path, parents)
                    current = snapshot_at(item["fd"], item["name"], missing=True)
                    if current == item["before"]:
                        continue
                    if current != item["after"]:
                        raise OSError("published asset changed; refuse rollback over a foreign edit")
                    if item["old"] is None:
                        os.unlink(item["name"], dir_fd=item["fd"])
                    else:
                        check_temporary(item, "old")
                        os.replace(item["old"], item["name"], src_dir_fd=item["fd"], dst_dir_fd=item["fd"])
                except (OSError, ValueError) as exc:
                    rollback_errors.append(type(exc).__name__)
            if rollback_errors:
                retained = True
                raise RuntimeError("publication rollback is contested or failed; preserve .sf-asset-* backups for recovery") from original
            raise
        finally:
            if not retained:
                try:
                    for item in prepared:
                        for key in ("new", "old"):
                            check_temporary(item, key, missing=True)
                    for item in prepared:
                        for key in ("new", "old"):
                            if item[key] is not None:
                                check_temporary(item, key, missing=True)
                                try:
                                    os.unlink(item[key], dir_fd=item["fd"])
                                except FileNotFoundError:
                                    pass
                except (OSError, ValueError) as exc:
                    retained = True
                    record_recovery()
                    raise RuntimeError("temporary cleanup is contested; preserve .sf-asset-* recovery files") from exc
            if retained:
                record_recovery()


def render(root=ROOT, cache=None, evidence=None):
    with termination_guard():
        return render_job(root, cache, evidence)


def render_job(root, cache, evidence):
    if sys.version_info < (3, 11) or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("asset rendering requires POSIX Python >=3.11")
    cache = Path(cache or os.environ.get("SF_RENDER_CACHE", ""))
    if not cache.is_absolute() or not (cache / "uv").is_dir() or not (cache / "browsers").is_dir():
        raise ValueError("prepare SF_RENDER_CACHE explicitly first; see docs/launch-assets.md")
    evidence = Path(evidence or os.environ.get("SF_RENDER_EVIDENCE", ""))
    if (not evidence.is_absolute() or evidence.is_symlink() or not evidence.is_dir()
            or evidence.resolve().is_relative_to(Path(root).resolve())
            or evidence.stat().st_uid != os.getuid() or evidence.stat().st_mode & 0o077):
        raise ValueError("set SF_RENDER_EVIDENCE to an owned private directory outside the checkout")
    evidence = Path(tempfile.mkdtemp(prefix="render-", dir=evidence))
    print(f"Private renderer evidence: {evidence}")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest, sources = load_sources(root_fd)
        with tempfile.TemporaryDirectory(prefix="sf-assets-") as temporary:
            outputs, observations = capture(manifest, sources, Path(temporary), cache, evidence)
            receipt = {"version": 1, "inputs": {name: digest(data) for name, data in sources.items()},
                       "outputs": {name: {"sha256": digest(data), "bytes": len(data),
                                           "dimensions": list(png_size(data))} for name, data in outputs.items()},
                       "evidence": observations}
            outputs["assets/render-receipt.json"] = encoded(receipt)
            publish(root_fd, outputs, Path(root).absolute(),
                    lambda record: private_log(evidence, "publication-recovery.json", encoded(record)))
    finally:
        os.close(root_fd)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        receipt = render()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zlib.error) as exc:
        parser.exit(1, f"assets: {exc}\n")
    print(f"Rendered {len(SIZES)} PNGs and 3 site copies; receipt: assets/render-receipt.json")
    print("Browser pixels still require visual review; no publication was performed.")
    return 0 if receipt else 1


if __name__ == "__main__":
    raise SystemExit(main())
