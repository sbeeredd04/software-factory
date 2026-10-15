"""Asset contracts and synthetic failure fixtures; real browser evidence is separate."""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_assets", ROOT / "scripts/render_assets.py")
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


def synthetic_png(width=2, height=2):
    """Valid solid pixels for TEMPORARY unit fixtures, never real output evidence."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress((b"\0" + b"\xf4\xf1\xe9" * width) * height)) + chunk(b"IEND", b"")


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sf-asset-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        (self.root / "site/img").mkdir(parents=True)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def sources(self):
        for name in render.INPUTS | {"assets/manifest.json"}:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        return json.loads((self.root / "assets/manifest.json").read_bytes())

    def outputs(self, old=False):
        names = [f"assets/{name}.png" for name in render.SIZES]
        names += [f"site/img/{name}.png" for name in ("loop", "team", "hosts")]
        names += ["assets/render-receipt.json"]
        result = {name: (b"old " if old else b"new ") + name.encode() for name in names}
        if old:
            for name, data in result.items():
                (self.root / name).write_bytes(data)
        return result

    def assert_outputs(self, expected):
        for name, data in expected.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)

    def test_manifest_has_finite_sources_and_seven_assets(self):
        self.sources()
        manifest, sources = render.load_sources(self.fd)
        self.assertEqual(len(manifest["assets"]), 7)
        self.assertEqual(set(sources), render.INPUTS | {"assets/manifest.json"})
        self.assertEqual([(entry["width"], entry["height"]) for entry in manifest["assets"]], list(render.SIZES.values()))
        for entry in manifest["assets"]:
            source = sources[entry["template"]].decode()
            self.assertIn('../../site/styles/tokens.css', source)
            self.assertIn('../../site/styles/base.css', source)
            self.assertIn('src="ready.js"', source)
            self.assertNotIn('https://', source)
            self.assertNotIn('style="', source)

    def test_invalid_manifest_and_unreviewed_fonts_fail(self):
        baseline = self.sources()
        mutations = [lambda m: m["inputs"].append("README.md"),
                     lambda m: m["assets"].append(m["assets"][0]),
                     lambda m: m["assets"][0].update(output="../foreign.png"),
                     lambda m: m["assets"][0].update(copies=["site/img/foreign.png"]),
                     lambda m: m["assets"][0].update(width=17),
                     lambda m: m["assets"][1].update(id="social-preview")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                manifest = copy.deepcopy(baseline)
                mutation(manifest)
                (self.root / "assets/manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    render.load_sources(self.fd)
        (self.root / "assets/manifest.json").write_text(json.dumps(baseline))
        (self.root / next(iter(render.FONTS))).write_bytes(b"changed font")
        with self.assertRaisesRegex(ValueError, "font source"):
            render.load_sources(self.fd)

    def test_read_boundaries_refuse_traversal_symlinks_and_special_files(self):
        for path in ("../outside", "/outside", "assets//x", "assets/./x", "assets/../x", "assets\\x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                render.read_at(self.fd, path)
        (self.root / "outside").write_bytes(b"private fixture")
        (self.root / "assets/link").symlink_to(self.root / "outside")
        with self.assertRaises(OSError):
            render.read_at(self.fd, "assets/link")
        (self.root / "linked").symlink_to(self.root / "assets", target_is_directory=True)
        with self.assertRaises(OSError):
            render.read_at(self.fd, "linked/link")
        os.mkfifo(self.root / "assets/pipe")
        with self.assertRaises(ValueError):
            render.read_at(self.fd, "assets/pipe")

    def test_png_validation_rejects_truncation_crc_and_invalid_stream(self):
        good = synthetic_png()
        self.assertEqual(render.png_size(good), (2, 2))
        for bad in (b"PNG", good[:-1], good + b"extra", good[:20] + b"x" + good[21:], good[:33]):
            with self.subTest(length=len(bad)), self.assertRaises((ValueError, zlib.error)):
                render.png_size(bad)
        self.assertEqual(render.png_size(synthetic_png(1280, 640)), (1280, 640))

    def test_png_empty_palette_is_rejected(self):
        good = synthetic_png()
        empty_palette = struct.pack(">I", 0) + b"PLTE" + struct.pack(">I", zlib.crc32(b"PLTE") & 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "palette"):
            render.png_size(good[:33] + empty_palette + good[33:])

    def test_launch_proof_requires_actual_safe_argv(self):
        safe = "pw:browser <launching> browser --headless --user-data-dir=private --remote-debugging-pipe\n"
        proof = render.launch_proof(safe)
        self.assertNotIn("private", json.dumps(proof))
        self.assertTrue(proof["chromium_sandbox"])
        for extra in ("--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security",
                      "--enable-unsafe-swiftshader", "--single-process", "--proxy-server=foreign"):
            with self.subTest(flag=extra), self.assertRaises(ValueError):
                render.launch_proof(safe.rstrip() + " " + extra)
        for bad in ("", "<launching> browser --headless", safe + safe):
            with self.assertRaises(ValueError):
                render.launch_proof(bad)

    def test_developer_helper_is_sandboxed_and_excluded_from_releases(self):
        source = (ROOT / "assets/tools/capture.py").read_text()
        tree = ast.parse(source)
        launches = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "launch"]
        self.assertEqual(len(launches), 1)
        options = {keyword.arg: ast.literal_eval(keyword.value) for keyword in launches[0].keywords if keyword.arg != "downloads_path"}
        self.assertIs(options["chromium_sandbox"], True)
        self.assertEqual(options["ignore_default_args"], ["--enable-unsafe-swiftshader"])
        self.assertNotIn("args", options)
        for forbidden in ("launch_persistent_context", "connect_over_cdp", "proxy=", "executable_path=", "--no-sandbox", "--disable-setuid-sandbox"):
            self.assertNotIn(forbidden, source)
        allowlist = json.loads((ROOT / "hosts/plugins/release-files.json").read_text())
        self.assertNotIn("assets/tools/capture.py", allowlist)
        self.assertNotIn("scripts/render_assets.py", allowlist)
        argv = render.developer_command(Path("capture.py"), Path("job.json"))
        self.assertIn("--offline", argv)
        self.assertIn("playwright==1.64.0", argv)
        self.assertNotIn("install", argv)
        self.assertNotIn("screenshot", argv)

    def test_readiness_requires_real_faces_decoded_images_and_bounded_layout(self):
        source = (ROOT / "assets/templates/ready.js").read_text()
        for contract in ("document.fonts.load", "matching.length", "face.status === 'loaded'", "image.decode()",
                         "naturalWidth", "scrollWidth", "scrollHeight", "securitypolicyviolation", "resources.some"):
            self.assertIn(contract, source)
        self.assertNotIn("document.fonts.check", source)
        manifest = self.sources()
        with self.assertRaises(ValueError):
            render.validate_report({"packages": render.VERSIONS, "captures": []}, manifest)

    def test_actual_ready_script_rejects_font_resource_decode_and_layout_failures(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable; readiness-script execution is unverified")
        result = subprocess.run([node, str(ROOT / "tests/fixtures/assets/readiness.cjs"),
                                 str(ROOT / "assets/templates/ready.js")], capture_output=True,
                                text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("6 synthetic readiness scenarios passed", result.stdout)

    def test_publish_prepares_complete_set_and_cleans_owned_temporaries(self):
        self.outputs(old=True)
        outputs = self.outputs()
        foreign = self.root / "assets/unrelated"
        foreign.write_bytes(b"keep")
        render.publish(self.fd, outputs)
        self.assert_outputs(outputs)
        self.assertEqual(foreign.read_bytes(), b"keep")
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_publish_rejects_incomplete_set_without_mutation(self):
        old = self.outputs(old=True)
        outputs = self.outputs()
        del outputs["assets/hero.png"]
        with self.assertRaises(ValueError):
            render.publish(self.fd, outputs)
        self.assert_outputs(old)

    def test_publish_rejects_symlink_target_and_parent_without_mutation(self):
        old = self.outputs(old=True)
        (self.root / "assets/hero.png").unlink()
        (self.root / "assets/hero.png").symlink_to(self.root / "assets/hosts.png")
        with self.assertRaises(OSError):
            render.publish(self.fd, self.outputs())
        self.assertEqual((self.root / "assets/hosts.png").read_bytes(), old["assets/hosts.png"])
        shutil.rmtree(self.root / "site/img")
        (self.root / "site/img").symlink_to(self.root / "assets", target_is_directory=True)
        with self.assertRaises(OSError):
            render.publish(self.fd, self.outputs())
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_preparation_failure_preserves_every_prior_file(self):
        old = self.outputs(old=True)
        with mock.patch.object(render.os, "fsync", side_effect=OSError("synthetic disk failure")), self.assertRaises(OSError):
            render.publish(self.fd, self.outputs())
        self.assert_outputs(old)
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_replaced_prepared_new_or_backup_is_never_moved_or_deleted(self):
        for target_kind in ("new", "backup"):
            with self.subTest(kind=target_kind):
                old = self.outputs(old=True)
                outputs = self.outputs()
                sought = outputs["assets/hero.png"] if target_kind == "new" else old["assets/hero.png"]
                original, count, foreign, records = render.os.fsync, 0, [], []

                def fsync(fd, sought=sought, foreign=foreign, original=original):
                    nonlocal count
                    count += 1
                    if count == 22:
                        path = next(path for path in (self.root / "assets").glob(".sf-asset-*") if path.read_bytes() == sought)
                        path.unlink()
                        path.write_bytes(b"foreign replacement of prepared temporary")
                        foreign.append(path)
                    return original(fd)

                with (mock.patch.object(render.os, "fsync", side_effect=fsync),
                      self.assertRaisesRegex(RuntimeError, "contested")):
                    render.publish(self.fd, outputs, self.root, records.append)
                self.assert_outputs(old)
                self.assertEqual(foreign[0].read_bytes(), b"foreign replacement of prepared temporary")
                self.assertEqual(len(records), 1)
                self.assertIn(foreign[0].name, json.dumps(records))
                # These are entirely owned synthetic-test files; prepare the next case.
                for path in self.root.rglob(".sf-asset-*"):
                    path.unlink()

    def test_replaced_backup_is_not_restored_over_a_published_file(self):
        old = self.outputs(old=True)
        outputs = self.outputs()
        original, count, foreign, records = render.os.replace, 0, [], []

        def replace(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                path = next(path for path in (self.root / "assets").glob(".sf-asset-*") if path.read_bytes() == old["assets/hero.png"])
                path.unlink()
                path.write_bytes(b"foreign backup during publication")
                foreign.append(path)
                raise OSError("synthetic replacement failure")
            return original(*args, **kwargs)

        with mock.patch.object(render.os, "replace", side_effect=replace), self.assertRaisesRegex(RuntimeError, "contested"):
            render.publish(self.fd, outputs, self.root, records.append)
        self.assertEqual((self.root / "assets/hero.png").read_bytes(), outputs["assets/hero.png"])
        self.assertEqual(foreign[0].read_bytes(), b"foreign backup during publication")
        self.assertEqual(len(records), 1)

    def test_cleanup_preserves_foreign_backup_replacement(self):
        old = self.outputs(old=True)
        original, count, foreign, records = render.os.fsync, 0, [], []

        def fsync(fd):
            nonlocal count
            count += 1
            if count == 23:
                path = next(path for path in (self.root / "assets").glob(".sf-asset-*") if path.read_bytes() == old["assets/hero.png"])
                path.unlink()
                path.write_bytes(b"foreign backup before cleanup")
                foreign.append(path)
            return original(fd)

        with mock.patch.object(render.os, "fsync", side_effect=fsync), self.assertRaisesRegex(RuntimeError, "contested"):
            render.publish(self.fd, self.outputs(), self.root, records.append)
        self.assertEqual(foreign[0].read_bytes(), b"foreign backup before cleanup")
        self.assertEqual(len(records), 1)

    def test_handled_replace_failure_rolls_back_previous_outputs(self):
        old = self.outputs(old=True)
        original, count = render.os.replace, 0

        def replace(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError("synthetic replacement failure")
            return original(*args, **kwargs)

        with mock.patch.object(render.os, "replace", side_effect=replace), self.assertRaises(OSError):
            render.publish(self.fd, self.outputs())
        self.assert_outputs(old)
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_failed_first_publication_removes_only_new_outputs(self):
        original, count = render.os.replace, 0

        def replace(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("synthetic failure")
            return original(*args, **kwargs)

        with mock.patch.object(render.os, "replace", side_effect=replace), self.assertRaises(OSError):
            render.publish(self.fd, self.outputs())
        self.assertEqual(list((self.root / "assets").iterdir()), [])
        self.assertEqual(list((self.root / "site/img").iterdir()), [])

    def test_interrupt_after_replace_effect_is_also_rolled_back(self):
        old = self.outputs(old=True)
        original, count = render.os.replace, 0

        def replace(*args, **kwargs):
            nonlocal count
            count += 1
            result = original(*args, **kwargs)
            if count == 3:
                raise KeyboardInterrupt("synthetic interruption after filesystem effect")
            return result

        with mock.patch.object(render.os, "replace", side_effect=replace), self.assertRaises(KeyboardInterrupt):
            render.publish(self.fd, self.outputs())
        self.assert_outputs(old)
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_contested_rollback_preserves_foreign_edit_and_recovery_backups(self):
        self.outputs(old=True)
        original, count = render.os.replace, 0
        first = min(self.outputs())

        def replace(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                (self.root / first).write_bytes(b"foreign edit after publication")
                raise OSError("synthetic failure after foreign edit")
            return original(*args, **kwargs)

        with mock.patch.object(render.os, "replace", side_effect=replace), self.assertRaisesRegex(RuntimeError, "contested"):
            render.publish(self.fd, self.outputs())
        self.assertEqual((self.root / first).read_bytes(), b"foreign edit after publication")
        self.assertTrue(list(self.root.rglob(".sf-asset-*")))

    def test_prepublication_contest_preserves_foreign_edit(self):
        self.outputs(old=True)
        original, count = render.os.fsync, 0
        target = self.root / "assets/hero.png"

        def fsync(fd):
            nonlocal count
            count += 1
            if count == 22:
                target.write_bytes(b"foreign preparation edit")
            return original(fd)

        with mock.patch.object(render.os, "fsync", side_effect=fsync), self.assertRaisesRegex(ValueError, "changed"):
            render.publish(self.fd, self.outputs())
        self.assertEqual(target.read_bytes(), b"foreign preparation edit")

    def test_parent_replacement_during_preparation_preserves_visible_foreign_tree(self):
        old = self.outputs(old=True)
        original, count = render.os.fsync, 0

        def fsync(fd):
            nonlocal count
            count += 1
            if count == 22:
                (self.root / "assets").rename(self.root / "retired-assets")
                (self.root / "assets").mkdir()
                (self.root / "assets/hero.png").write_bytes(b"foreign parent tree")
            return original(fd)

        with mock.patch.object(render.os, "fsync", side_effect=fsync), self.assertRaisesRegex(ValueError, "parent changed"):
            render.publish(self.fd, self.outputs(), self.root)
        self.assertEqual((self.root / "assets/hero.png").read_bytes(), b"foreign parent tree")
        self.assertEqual((self.root / "retired-assets/hero.png").read_bytes(), old["assets/hero.png"])
        self.assertEqual(list(self.root.rglob(".sf-asset-*")), [])

    def test_replaced_visible_checkout_root_is_not_published_through_held_fd(self):
        old = self.outputs(old=True)
        retired = self.root.with_name(self.root.name + "-retired")
        self.addCleanup(shutil.rmtree, retired)
        self.root.rename(retired)
        self.root.mkdir()
        (self.root / "foreign").write_bytes(b"new checkout")
        with self.assertRaisesRegex(ValueError, "root changed"):
            render.publish(self.fd, self.outputs(), self.root)
        self.assertEqual((self.root / "foreign").read_bytes(), b"new checkout")
        self.assertEqual((retired / "assets/hero.png").read_bytes(), old["assets/hero.png"])

    def test_capture_failures_preserve_prior_set(self):
        self.sources()
        old = self.outputs(old=True)
        cache = self.root / "cache"
        (cache / "uv").mkdir(parents=True)
        (cache / "browsers").mkdir()
        with tempfile.TemporaryDirectory(prefix="sf-private-evidence-test-") as external:
            for error in (ValueError("unsafe launch proof"), ValueError("font readiness failed"),
                          ValueError("wrong PNG dimensions"), render.subprocess.TimeoutExpired("fixture", 1)):
                with (self.subTest(error=error), mock.patch.object(render, "capture", side_effect=error),
                      mock.patch.object(render, "publish") as publish, mock.patch("builtins.print"), self.assertRaises(type(error))):
                    render.render(self.root, cache, Path(external))
                publish.assert_not_called()
                self.assert_outputs(old)

    def test_child_timeout_terminates_only_its_process_group(self):
        process = mock.Mock(pid=23456)
        process.communicate.side_effect = [render.subprocess.TimeoutExpired("fixture", 1), ("", "")]
        with (mock.patch.object(render.subprocess, "Popen", return_value=process) as popen,
              mock.patch.object(render.os, "killpg") as kill, self.assertRaises(render.subprocess.TimeoutExpired)):
            render.run_child(["synthetic-fixture"], {}, self.root, timeout=1)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        kill.assert_called_once_with(23456, render.signal.SIGTERM)
        self.assertTrue((self.root / "capture-stderr.log").is_file())

    def test_failed_child_keeps_raw_stderr_private_and_error_concise(self):
        process = mock.Mock(pid=23456, returncode=1)
        process.communicate.return_value = ("", "synthetic private profile detail")
        with (mock.patch.object(render.subprocess, "Popen", return_value=process),
              mock.patch.object(render.os, "killpg"), self.assertRaises(ValueError) as raised):
            render.run_child(["synthetic-fixture"], {}, self.root)
        self.assertNotIn("profile detail", str(raised.exception))
        self.assertEqual((self.root / "capture-stderr.log").read_text(), "synthetic private profile detail")
        self.assertEqual((self.root / "capture-stderr.log").stat().st_mode & 0o777, 0o600)

    def test_sigterm_reaps_actual_owned_python_child_and_retains_private_log(self):
        evidence = self.root / "private-evidence"
        evidence.mkdir(mode=0o700)
        pidfile = self.root / "owned-child.pid"
        process = subprocess.Popen([sys.executable, str(ROOT / "tests/fixtures/assets/sigterm_controller.py"),
                                    str(render.__file__), str(pidfile), str(evidence)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child = None
        try:
            deadline = time.monotonic() + 5
            while not pidfile.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(0.01)
            self.assertTrue(pidfile.exists(), "synthetic child failed to start")
            child = int(pidfile.read_text())
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, -signal.SIGTERM)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)
            self.assertTrue((evidence / "capture-stderr.log").is_file())
            self.assertEqual((evidence / "capture-stderr.log").stat().st_mode & 0o777, 0o600)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            if child is not None:
                try:
                    os.killpg(child, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_missing_cache_fails_before_capture_or_publication(self):
        old = self.outputs(old=True)
        with (mock.patch.object(render, "capture") as capture, mock.patch.object(render, "publish") as publish,
              self.assertRaisesRegex(ValueError, "prepare SF_RENDER_CACHE")):
            render.render(self.root, self.root / "absent-cache")
        capture.assert_not_called()
        publish.assert_not_called()
        self.assert_outputs(old)

    def test_published_assets_receipt_aliases_and_references(self):
        manifest = json.loads((ROOT / "assets/manifest.json").read_text())
        receipt = json.loads((ROOT / "assets/render-receipt.json").read_text())
        for entry in manifest["assets"]:
            data = (ROOT / entry["output"]).read_bytes()
            self.assertEqual(render.png_size(data), (entry["width"], entry["height"]))
            for name in [entry["output"], *entry["copies"]]:
                self.assertEqual((ROOT / name).read_bytes(), data)
                self.assertEqual(receipt["outputs"][name]["sha256"], render.digest(data))
        for name in manifest["inputs"] + ["assets/manifest.json"]:
            self.assertEqual(receipt["inputs"][name], render.digest((ROOT / name).read_bytes()), name)
        self.assertIn('assets/hero.png', (ROOT / "README.md").read_text())
        self.assertIn('docs/launch-assets.md', (ROOT / "README.md").read_text())
        allowlist = json.loads((ROOT / "hosts/plugins/release-files.json").read_text())
        self.assertIn('assets/hero.png', allowlist)
        self.assertIn('docs/launch-assets.md', allowlist)
        for name in ("loop", "team", "hosts"):
            self.assertIn(f'src="img/{name}.png"', (ROOT / "site/index.html").read_text())


if __name__ == "__main__":
    unittest.main()
