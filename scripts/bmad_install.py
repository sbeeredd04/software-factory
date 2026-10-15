"""Pinned, separately committed BMad provisioning with conservative reuse.

This invokes the official npm installer in the actual consumer directory.
It does not sandbox upstream code or roll back its effects. BMad provenance
never adds deletion rights to the factory's owned-file manifest.
"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
from pathlib import Path

VERSION = "6.12.0"
PACKAGE = f"bmad-method@{VERSION}"
MANIFEST = "_bmad/_config/manifest.yaml"
MODULES = ("core", "bmm", "bmb", "cis", "tea")
PREREQUISITES = ("node", "npm", "npx", "uv", "git")
INSTALL_TIMEOUT = 300
PROBE_TIMEOUT = 10
MAX_MANIFEST_BYTES = 512 * 1024


def scalar(text):
    """Only the scalar forms emitted by the pinned manifest writer."""
    if text in ("null", "~"):
        return None
    if text in ("true", "false"):
        return text == "true"
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text.startswith('"'):
        value = json.loads(text)
        if not isinstance(value, str):
            raise ValueError("unsupported scalar")
        return value
    if text.startswith("'"):
        if not text.endswith("'") or re.search(r"(?<!')'(?!')", text[1:-1]):
            raise ValueError("unsupported quote")
        return text[1:-1].replace("''", "'")
    if not text or text[0] in "[{}]!&*|>@`" or "\t" in text:
        raise ValueError("unsupported YAML syntax")
    return re.split(r"\s+#", text, maxsplit=1)[0]


def parse_manifest(content):
    """Bounded known-writer YAML subset, not a general YAML parser.

    Supports indented maps/lists, list maps and scalar values; rejects tags,
    aliases, multiline/flow collections, duplicate keys and odd indentation.
    """
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest above limit")
    text = content.decode("utf-8")
    if text.lstrip().startswith("{"):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        data = json.loads(text, object_pairs_hook=unique)
    else:
        rows = []
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indentation = len(line) - len(line.lstrip(" "))
            if indentation % 2 or indentation > 16 or "\t" in line:
                raise ValueError("unsupported indentation")
            rows.append((indentation, line.strip()))
        if not rows or len(rows) > 10000 or rows[0][0] != 0:
            raise ValueError("invalid manifest")

        def field(line):
            matched = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*):(?: (.*))?", line)
            if not matched:
                raise ValueError("unsupported mapping")
            return matched[1], matched[2]

        def block(index, depth):
            is_list = rows[index][1].startswith("- ")
            result = [] if is_list else {}
            while index < len(rows) and rows[index][0] == depth:
                line = rows[index][1]
                if is_list:
                    if not line.startswith("- "):
                        raise ValueError("mixed collection")
                    body = line[2:]
                    if re.match(r"[A-Za-z][A-Za-z0-9_]*:", body):
                        key, value = field(body)
                        if value is None:
                            raise ValueError("unsupported nested list item")
                        item = {key: scalar(value)}
                        index += 1
                        if index < len(rows) and rows[index][0] > depth:
                            if rows[index][0] != depth + 2:
                                raise ValueError("invalid list indentation")
                            rest, index = block(index, depth + 2)
                            if not isinstance(rest, dict) or key in rest:
                                raise ValueError("invalid list mapping")
                            item.update(rest)
                        result.append(item)
                    else:
                        result.append(scalar(body))
                        index += 1
                else:
                    key, value = field(line)
                    if key in result:
                        raise ValueError("duplicate key")
                    index += 1
                    if value is None:
                        if index >= len(rows) or rows[index][0] != depth + 2:
                            raise ValueError("missing nested value")
                        value, index = block(index, depth + 2)
                    else:
                        value = scalar(value)
                    result[key] = value
            return result, index

        data, end = block(0, 0)
        if end != len(rows):
            raise ValueError("unconsumed manifest")
    if not isinstance(data, dict) or not isinstance(data.get("installation"), dict):
        raise TypeError("missing installation metadata")
    version = data["installation"].get("version")
    if version is not None and not isinstance(version, str):
        raise ValueError("invalid version")
    modules, ides = data.get("modules"), data.get("ides")
    if not isinstance(modules, list) or not isinstance(ides, list) or not all(isinstance(i, str) for i in ides):
        raise ValueError("invalid modules or tools")
    normalized = []
    seen = set()
    for module in modules:
        if isinstance(module, str):
            module = {"name": module, "version": None}
        if not isinstance(module, dict) or not isinstance(module.get("name"), str) or module["name"] in seen:
            raise ValueError("invalid module")
        seen.add(module["name"])
        record = {"name": module["name"], "version": module.get("version")}
        for key in ("source", "channel", "sha"):
            if key in module:
                record[key] = module[key]
        if any(value is not None and not isinstance(value, str) for value in record.values()):
            raise ValueError("invalid module provenance")
        normalized.append(record)
    return {"version": version, "modules": normalized, "ides": ides}


def contained(root, rel):
    """No symlink traversal, even for a path that resolves inside the project."""
    path = root
    for part in Path(rel).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("symlinked provisioning path")
    return path


def discovered(root):
    for rel in ("_bmad", "_bmad-output", ".bmad", ".bmad-core", ".bmad-method"):
        path = root / rel
        if path.exists() or path.is_symlink():
            return True
    for base in (".claude/skills", ".agents/skills", ".cursor/skills", ".codex/skills",
                 ".claude/commands", ".cursor/rules", ".codex/prompts"):
        try:
            directory = contained(root, base)
            if directory.is_dir() and any(p.name.lower().startswith("bmad") for p in directory.iterdir()):
                return True
        except (OSError, ValueError):
            return True  # Unknown ownership is not permission to provision.
    return False


def read_payload(root, rel, limit):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = Path(rel).parts
        if Path(rel).is_absolute() or any(part in (".", "..") for part in parts):
            raise ValueError("unsafe payload path")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(source, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("payload is not a regular file")
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError("payload above limit")
        return content
    finally:
        os.close(descriptor)


def observe(root):
    record = {"version": None, "modules": [], "ides": [], "manifest": None,
              "manifest_sha256": None}
    try:
        content = read_payload(root, MANIFEST, MAX_MANIFEST_BYTES)
        record.update(manifest=MANIFEST, manifest_sha256=hashlib.sha256(content).hexdigest())
        record.update(parse_manifest(content))
    except (OSError, ValueError, TypeError):
        return record, False
    return record, True


def command(root, hosts):
    return ["npx", "-y", PACKAGE, "install", "--directory", str(root),
            "--tools", ",".join(hosts), "--modules", "bmm,bmb,cis,tea", "--yes"]


def prerequisites():
    if any(shutil.which(name) is None for name in PREREQUISITES):
        return {}, "missing prerequisites; install Node >=20.12, compatible npm/npx, uv and Git, then retry"
    versions = {}
    for name in ("node", "npm"):
        try:
            result = subprocess.run([name, "--version"], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False)
            value = result.stdout.strip()
            matched = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.-]+)?", value)
            if result.returncode or not matched:
                raise ValueError("unknown version")
            versions[name] = value
            if name == "node" and tuple(map(int, matched.groups())) < (20, 12, 0):
                return versions, "Node below supported floor; install Node >=20.12 and compatible npm/npx, then retry"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return versions, f"{name} version unavailable; install Node >=20.12 and compatible npm/npx, then retry"
    return versions, None


def invoke(root, hosts):
    """Close stdin and suppress raw upstream identity/credential-bearing output."""
    process = subprocess.Popen(command(root, hosts), cwd=root, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    try:
        return process.wait(timeout=INSTALL_TIMEOUT), False
    except BaseException as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if isinstance(exc, subprocess.TimeoutExpired):
            return None, True
        raise


def complete(root, hosts, record):
    modules = {m["name"]: m for m in record["modules"]}
    if (record["version"] != VERSION or not set(MODULES) <= modules.keys()
            or any(modules[name]["version"] != VERSION for name in ("core", "bmm"))
            or not set(hosts) <= set(record["ides"])):
        return False
    try:
        # The pinned writer inventories canonical skill IDs and module owners;
        # its cleanup removes redundant skill copies from module directories.
        content = read_payload(root, "_bmad/_config/skill-manifest.csv", 4 * 1024 * 1024)
        rows = csv.DictReader(io.StringIO(content.decode("utf-8")), strict=True)
        if rows.fieldnames != ["canonicalId", "name", "description", "module", "path"]:
            return False
        bases = []
        if "claude-code" in hosts:
            bases.append(".claude/skills")
        if set(hosts) & {"cursor", "codex"}:
            bases.append(".agents/skills")
        covered, identifiers = set(), set()
        for row in rows:
            identifier = row.get("canonicalId")
            if (set(row) != set(rows.fieldnames) or not isinstance(identifier, str)
                    or not re.fullmatch(r"bmad-[a-z0-9][a-z0-9-]{0,127}", identifier)
                    or identifier in identifiers or row["module"] not in modules):
                return False
            identifiers.add(identifier)
            for base in bases:
                skill = read_payload(root, f"{base}/{identifier}/SKILL.md", 4 * 1024 * 1024)
                if not skill.strip():
                    return False
            covered.add(row["module"])
        return set(MODULES) <= covered
    except (OSError, ValueError, TypeError, csv.Error):
        return False


def describe(record):
    """Only validated public identifiers enter human-readable diagnostics."""
    def version(value):
        if isinstance(value, str) and re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]{1,40})?", value) and not re.search(
            r"gh[pousr]_|github_pat_|sk-|AKIA", value
        ):
            return value
        return "unknown"
    modules = {module["name"]: module for module in record["modules"]}
    detail = ", ".join(f"{name}={version(modules[name]['version'])}" for name in MODULES if name in modules)
    tools = ", ".join(name for name in ("claude-code", "cursor", "codex") if name in record["ides"])
    print(f"install: BMad observed version {version(record['version'])}; modules: {detail or 'unknown'}; tools: {tools or 'unknown'}")


def attempt(root, hosts, before_invoke=None):
    """One independent upstream attempt, or preservation/degraded observation."""
    record = {"package": PACKAGE, "requested_version": VERSION, "tools": hosts,
              "status": "existing", "reason": "existing or partial BMad preserved; no update invoked",
              "runtime_versions": {}, **observe(root)[0]}
    if discovered(root):
        return record
    versions, problem = prerequisites()
    record["runtime_versions"] = versions
    if problem:
        return {**record, "status": "degraded", "reason": problem}
    if before_invoke is not None:
        before_invoke({**record, "status": "failed", "exit_code": None,
                       "reason": "upstream attempt started; completion unverified; inspect partial effects before manual retry"})
    try:
        code, timeout = invoke(root, hosts)
    except OSError:
        code, timeout = None, False
    observed, parsed = observe(root)
    record.update(observed)
    record.update(exit_code=code)
    if not timeout and code == 0 and parsed and complete(root, hosts, record):
        record.update(status="installed", reason="manifest and per-module host skill presence verified; external modules and npm dependencies may float; live use unverified")
    else:
        reason = "timed out" if timeout else f"exited {code} or produced incomplete output"
        record.update(status="failed", reason=f"upstream {reason}; partial effects retained; inspect BMad files before any manual recovery; no automatic retry")
    return record


def save_record(root, previous, record, api):
    """Use the existing anchored publication primitive, retaining recovery copies."""
    spec = importlib.util.spec_from_file_location("sf_bmad_lifecycle", Path(__file__).with_name("install_lifecycle.py"))
    lifecycle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lifecycle)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with lifecycle.parent_fd(root_fd, api.MANIFEST_REL) as (fd, name):
            before = lifecycle.read_at(fd, name)
            if before is None or json.loads(before) != previous:
                raise api.InstallError("ownership changed during BMad provisioning; partial upstream effects may remain; reconcile manually")
            updated = {**previous, "bmad": record}
            quarantine, _ = lifecycle.recovery_directory(root_fd)
            try:
                lifecycle.publish(fd, name, (json.dumps(updated, indent=2) + "\n").encode(),
                                  expected=before, quarantine=quarantine, relative=api.MANIFEST_REL)
            finally:
                os.close(quarantine)
            return updated
    finally:
        os.close(root_fd)


def provision(root, hosts, api):
    """Second transaction: serialize upstream work and persist provenance only."""
    fd, _ = api.acquire_lock(root, set())
    try:
        previous = api.load_manifest(root)
        if previous is None:
            raise api.InstallError("factory ownership disappeared before BMad provisioning; retry")
        prior_bmad = previous.get("bmad")
        if isinstance(prior_bmad, dict) and prior_bmad.get("status") == "failed":
            print("install: BMad failed attempt retained; inspect partial effects and installation metadata before manual retry")
            return 0

        def started(record):
            nonlocal previous
            previous = save_record(root, previous, record, api)

        record = attempt(root, hosts, started)
        drift = False
        for entry in previous["files"]:
            try:
                content = api.read_file(contained(root, entry["path"]), entry["path"])
                drift |= content is None or api.sha256(content) != entry["sha256"]
            except (OSError, ValueError, api.InstallError):
                drift = True
        if drift:
            record.update(status="failed", reason="factory-owned files changed during provisioning; preserve edits and reconcile manually; partial upstream effects retained")
        if record != prior_bmad:
            save_record(root, previous, record, api)
        print(f"install: BMad {record['status']}: {record['reason']}")
        describe(record)
        return int(drift)
    except (OSError, ValueError) as exc:
        raise api.InstallError("BMad metadata phase failed; upstream effects and private backup receipts may remain; inspect before retrying") from exc
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
