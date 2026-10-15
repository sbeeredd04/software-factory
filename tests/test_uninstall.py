"""Uninstall ownership, restoration and transaction regressions."""
from __future__ import annotations

import importlib.util
import io
import json
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("sf_support", Path(__file__).with_name("support.py"))
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)
_spec = importlib.util.spec_from_file_location("sf_lifecycle", support.REPO / "scripts/install_lifecycle.py")
lifecycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lifecycle)


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-uninstall-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.repo = support.existing_repo(self.temp)
        self.env, self.guard, stub = support.guard_env()
        self.addCleanup(shutil.rmtree, stub, ignore_errors=True)
        self.home, self.snapshot_home = support.home_sentinel(self.temp)
        self.env["HOME"] = str(self.home)
        self.home_before = self.snapshot_home()
        self.api = types.SimpleNamespace(**runpy.run_path(str(support.INSTALLER)))

    def tearDown(self):
        self.assertFalse(self.guard.exists())
        self.assertEqual(self.home_before, self.snapshot_home())

    def install(self, host="all", *args):
        result = support.run_installer("install", "--project", self.repo, "--host", host,
                                       "--skip-bmad", *args, env=self.env)
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def uninstall(self, host="all", *args):
        return support.run_installer("uninstall", "--project", self.repo,
                                     "--host", host, *args, env=self.env)

    def manifest(self):
        return json.loads((self.repo / self.api.MANIFEST_REL).read_text())

    def test_dry_run_and_full_uninstall_preserve_user_state_and_retry(self):
        originals = {name: (self.repo / name).read_bytes() for name in ("CLAUDE.md", "AGENTS.md")}
        keep = (".software-factory/config.yaml", ".software-factory/context/notes.md",
                ".software-factory/overlays/x.md", ".software-factory/runs/demo/run.json",
                "PRINCIPLES.md", "_bmad/_config/manifest.yaml")
        for rel in keep:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("user-owned fixture\n")
        # Registered overlays require validated config before composition. Keep
        # real user-owned config bytes rather than a malformed placeholder.
        configuration = json.loads((support.REPO / "examples/config/config.yaml").read_text())
        configuration["project"]["root"] = ".."
        for name in ("PRODUCT.md", "CONVENTIONS.md", "RISK.md", "EVALS.md", "ARCHITECTURE.md", "TASKS.md"):
            shutil.copyfile(support.REPO / "examples/config" / name, self.repo / name)
        (self.repo / ".software-factory/config.yaml").write_text(json.dumps(configuration))
        self.install()
        before = support.tree_hashes(self.repo)
        dry = self.uninstall("all", "--dry-run")
        self.assertEqual(0, dry.returncode, dry.stderr)
        self.assertIn("remove", dry.stdout)
        self.assertEqual(before, support.tree_hashes(self.repo))
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        after = support.tree_hashes(self.repo)
        for rel in keep:
            self.assertEqual(before[rel], after[rel])
        for name, content in originals.items():
            self.assertEqual(content, (self.repo / name).read_bytes())
        for rel in (".claude/skills", ".claude/agents", ".cursor/agents", ".codex/agents",
                    ".agents/skills", self.api.RUNTIME_REL, self.api.MANIFEST_REL):
            self.assertFalse((self.repo / rel).exists(), rel)
        for rel, expected in ((".claude/settings.json", support.CLAUDE_SETTINGS_FIXTURE),
                              (".cursor/hooks.json", support.CURSOR_HOOKS_FIXTURE)):
            self.assertEqual(json.loads(expected), json.loads((self.repo / rel).read_text()))
        self.assertTrue((self.repo / self.api.LOCK_REL).is_file())
        ignores = (self.repo / ".gitignore").read_text().splitlines()
        self.assertIn("build/", ignores)
        self.assertIn(".env", ignores)
        for entry in self.api.GITIGNORE_ENTRIES:
            self.assertIn(entry, ignores)
        self.assertNotIn(".software-factory/", ignores)
        self.assertEqual(0, self.uninstall().returncode)
        self.assertEqual(after, support.tree_hashes(self.repo))

    def test_dry_run_from_fresh_pack_does_not_write_source_caches(self):
        self.install("cursor")
        copied = self.temp / "fresh-pack"
        shutil.copytree(support.REPO, copied,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        before_pack = support.tree_hashes(copied)
        before_project = support.tree_hashes(self.repo)
        env = {**self.env}
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run([sys.executable, str(copied / "install.py"), "uninstall",
                                 "--project", str(self.repo), "--dry-run"],
                                env=env, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before_pack, support.tree_hashes(copied))
        self.assertEqual(before_project, support.tree_hashes(self.repo))
        self.assertEqual([], list(copied.rglob("__pycache__")))

    def test_edits_and_unknown_files_survive_with_manual_followup(self):
        self.install()
        rel = ".claude/skills/sf-patterns/SKILL.md"
        target = self.repo / rel
        target.write_text(target.read_text() + "\n# user note\n")
        unknown = self.repo / ".claude/agents/user.txt"
        unknown.write_text("keep")
        empty = self.repo / ".claude/skills/user-empty"
        empty.mkdir()
        settings = self.repo / ".claude/settings.json"
        doc = json.loads(settings.read_text())
        doc["hooks"]["SessionStart"].append({"hooks": [{"command": "echo user"}]})
        settings.write_text(json.dumps(doc))
        agents = self.repo / "AGENTS.md"
        agents.write_text(agents.read_text() + "new user prose\n")
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(rel, result.stdout)
        self.assertIn("manual", result.stdout)
        self.assertIn("user note", target.read_text())
        self.assertEqual("keep", unknown.read_text())
        self.assertTrue(empty.is_dir())
        self.assertIn("new user prose", agents.read_text())
        self.assertNotIn(self.api.BLOCK_BEGIN, agents.read_text())
        cleaned = json.loads(settings.read_text())
        self.assertEqual([{ "hooks": [{"command": "echo user"}]}], cleaned["hooks"]["SessionStart"])
        self.assertEqual(doc["permissions"], cleaned["permissions"])

    def test_original_restore_survives_updates_and_tampered_backup_is_refused(self):
        rel = ".cursor/rules/software-factory.mdc"
        path = self.repo / rel
        path.parent.mkdir(parents=True)
        path.write_text("original user rule\n")
        self.install("cursor", "--allow-overwrite", rel)
        original = next(e["restore"] for e in self.manifest()["files"] if e["path"] == rel)
        path.write_text("intermediate user modification\n")
        self.install("cursor", "--allow-overwrite", rel)
        self.install("codex")
        entry = next(e for e in self.manifest()["files"] if e["path"] == rel)
        self.assertEqual(original, entry["restore"])
        self.assertEqual("intermediate user modification\n", (self.repo / entry["backup"]).read_text())
        backup = self.repo / original["path"]
        backup.write_text("tampered backup\n")
        before = support.tree_hashes(self.repo)
        result = self.uninstall()
        self.assertEqual(1, result.returncode)
        self.assertIn("backup", result.stderr)
        self.assertEqual(before, support.tree_hashes(self.repo))
        backup.write_text("original user rule\n")
        self.assertEqual(0, self.uninstall().returncode)
        self.assertEqual("original user rule\n", path.read_text())
        self.assertTrue(backup.is_file())

    def test_selective_host_removal_reprojects_shared_policy_and_retains_runtime(self):
        self.install()
        self.assertEqual(0, self.uninstall("cursor").returncode)
        data = self.manifest()
        self.assertEqual(["claude-code", "codex"], data["hosts"])
        skill = self.repo / ".agents/skills/software-factory/SKILL.md"
        self.assertNotIn("disable-model-invocation", skill.read_text())
        self.assertTrue((skill.parent / "agents/openai.yaml").exists())
        self.assertTrue((self.repo / self.api.RUNTIME_REL).is_dir())
        for entry in data["files"]:
            self.assertEqual(entry["sha256"], self.api.sha256((self.repo / entry["path"]).read_bytes()))
        snapshot = support.tree_hashes(self.repo)
        self.assertEqual(0, self.uninstall("cursor").returncode)
        self.assertEqual(snapshot, support.tree_hashes(self.repo))
        self.install("cursor")
        self.assertEqual(0, self.uninstall("codex").returncode)
        self.assertIn("disable-model-invocation: true", skill.read_text())
        self.assertFalse((skill.parent / "agents/openai.yaml").exists())
        self.assertEqual(0, self.uninstall("claude-code").returncode)
        self.assertTrue((self.repo / self.api.RUNTIME_REL).is_dir())

    def test_selective_changed_shared_skill_and_mixed_profiles(self):
        self.install("cursor", "--profile", "skills-only")
        self.install("codex")
        skill = self.repo / ".agents/skills/software-factory/SKILL.md"
        skill.write_text(skill.read_text() + "local change\n")
        result = self.uninstall("codex")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("local change", skill.read_text())
        self.assertIn("retained edited", result.stdout)
        self.assertFalse((self.repo / self.api.RUNTIME_REL).exists())
        self.assertEqual("skills-only", self.manifest()["profile"])

    def test_malicious_manifest_and_symlink_refuse_before_mutation(self):
        self.install()
        file = self.repo / self.api.MANIFEST_REL
        original = file.read_bytes()
        protected = self.repo / ".software-factory/config.yaml"
        protected.write_text("do not delete\n")
        for bad in (".software-factory/config.yaml", "../outside", ".git/config", "PRINCIPLES.md"):
            data = json.loads(original)
            data["files"][0]["path"] = bad
            data["files"][0]["sha256"] = self.api.sha256(protected.read_bytes())
            file.write_text(json.dumps(data))
            before = support.tree_hashes(self.repo)
            result = self.uninstall()
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertEqual(before, support.tree_hashes(self.repo))
        file.write_bytes(original)
        target = self.repo / ".claude/skills/sf-patterns/SKILL.md"
        target.unlink()
        target.symlink_to(protected)
        before = support.tree_hashes(self.repo)
        result = self.uninstall()
        self.assertEqual(1, result.returncode)
        self.assertEqual(before, support.tree_hashes(self.repo))
        self.assertEqual("do not delete\n", protected.read_text())

    def test_edited_settings_remove_adapter_from_a_different_python_without_execution(self):
        self.install("claude-code")
        settings = self.repo / ".claude/settings.json"
        doc = json.loads(settings.read_text())
        for groups in doc["hooks"].values():
            for group in groups:
                for handler in group["hooks"]:
                    if "runtime/hook.py" in handler.get("command", ""):
                        argv = shlex.split(handler["command"].removesuffix(" 2>&1"))
                        argv[0] = str(self.temp / "different-python" / "python3")
                        handler["command"] = shlex.join(argv) + " 2>&1"
        doc["userSetting"] = "preserve"
        settings.write_text(json.dumps(doc))
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        cleaned = json.loads(settings.read_text())
        self.assertEqual("preserve", cleaned["userSetting"])
        self.assertEqual(doc["hooks"]["PreToolUse"], cleaned["hooks"]["PreToolUse"])
        self.assertNotIn("runtime/hook.py", settings.read_text())

    def test_moved_edited_settings_report_stale_adapters_without_removing_user_hooks(self):
        self.install("claude-code")
        moved = self.temp / "moved"
        shutil.copytree(self.repo, moved)
        self.repo = moved
        settings = self.repo / ".claude/settings.json"
        doc = json.loads(settings.read_text())
        doc["userSetting"] = "preserve"
        settings.write_text(json.dumps(doc))
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("remove stale or ambiguous adapters manually", result.stdout)
        cleaned = json.loads(settings.read_text())
        self.assertEqual("preserve", cleaned["userSetting"])
        self.assertEqual(doc["hooks"]["PreToolUse"], cleaned["hooks"]["PreToolUse"])
        self.assertIn("runtime/hook.py", settings.read_text())

    def test_stale_plan_and_interrupt_roll_back_without_losing_backups(self):
        self.install()
        _, observed, changes, _ = lifecycle.plan_uninstall(self.repo, ["cursor"], self.api)
        self.install("claude-code", "--profile", "skills-only")
        manifest_path = self.repo / self.api.MANIFEST_REL
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        before = support.tree_hashes(self.repo)
        with self.assertRaisesRegex(self.api.InstallError, "changed while planning"):
            lifecycle.apply_uninstall(self.repo, observed, changes, self.api)
        self.assertEqual(before, support.tree_hashes(self.repo))
        _, observed, changes, _ = lifecycle.plan_uninstall(self.repo, ["cursor"], self.api)
        original = lifecycle.publish
        calls = 0

        def fail_once(path, content, directories, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            return original(path, content, directories, **kwargs)

        with mock.patch.object(lifecycle, "publish", side_effect=fail_once), self.assertRaises(KeyboardInterrupt):
            lifecycle.apply_uninstall(self.repo, observed, changes, self.api)
        recovered = support.tree_hashes(self.repo)
        self.assertEqual(before, {rel: digest for rel, digest in recovered.items() if rel in before})
        self.assertTrue(all(rel.startswith(".software-factory/backups/uninstall-")
                            for rel in recovered.keys() - before.keys()))

    def test_selective_removal_preserves_installed_version_bodies(self):
        self.install()
        paths = [".agents/skills/software-factory/SKILL.md",
                 ".agents/skills/software-factory/scripts/hook.py"]
        # Model a prior released pack with owned, valid but different bodies.
        manifest_path = self.repo / self.api.MANIFEST_REL
        data = self.manifest()
        for rel in paths:
            path = self.repo / rel
            path.write_bytes(path.read_bytes() + b"\n# prior version body\n")
            next(e for e in data["files"] if e["path"] == rel)["sha256"] = self.api.sha256(path.read_bytes())
        manifest_path.write_text(json.dumps(data))
        expected = {rel: (self.repo / rel).read_bytes() for rel in paths}
        result = self.uninstall("cursor")
        self.assertEqual(0, result.returncode, result.stderr)
        for rel in paths:
            self.assertEqual(expected[rel].replace(b"disable-model-invocation: true\n", b""),
                             (self.repo / rel).read_bytes())

    def test_ancestor_swap_cannot_mutate_external_targets(self):
        self.install("cursor")
        rel = ".agents/skills/software-factory/SKILL.md"
        target = self.repo / rel
        before = target.read_bytes()
        outside = self.temp / "outside"
        outside.mkdir()
        (outside / target.name).write_bytes(before)
        parent = target.parent
        saved = parent.with_name("displaced")
        original = lifecycle.publish

        def swap(fd, name, content, **kwargs):
            parent.rename(saved)
            parent.symlink_to(outside, target_is_directory=True)
            return original(fd, name, content, **kwargs)

        with mock.patch.object(lifecycle, "publish", side_effect=swap):
            lifecycle.apply_uninstall(self.repo, {rel: before}, [(rel, before, None)], self.api)
        self.assertEqual(before, (outside / target.name).read_bytes())
        self.assertFalse((saved / target.name).exists())

    def test_contested_rollback_continues_restoring_independent_entries(self):
        self.install("cursor")
        paths = ["AGENTS.md", ".cursor/rules/software-factory.mdc", ".gitignore"]
        observed = {rel: (self.repo / rel).read_bytes() for rel in paths}
        changes = [(rel, observed[rel], b"transaction") for rel in paths]
        original = lifecycle.publish
        calls = 0
        outside = self.temp / "outside"
        outside.mkdir()
        victim = self.repo / paths[1]
        (outside / victim.name).write_bytes(b"external")

        def fail(fd, name, content, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                victim.parent.rename(victim.parent.with_name("displaced"))
                victim.parent.symlink_to(outside, target_is_directory=True)
                raise KeyboardInterrupt()
            return original(fd, name, content, **kwargs)

        report = io.StringIO()
        with (mock.patch.object(lifecycle, "publish", side_effect=fail), redirect_stderr(report),
              self.assertRaises(KeyboardInterrupt)):
            lifecycle.apply_uninstall(self.repo, observed, changes, self.api)
        self.assertEqual(observed[paths[0]], (self.repo / paths[0]).read_bytes())
        self.assertEqual(b"external", (outside / victim.name).read_bytes())
        self.assertIn("retained contested", report.getvalue())

    def test_final_component_replacement_is_captured_and_preserved(self):
        self.install("cursor")
        rel = "AGENTS.md"
        target = self.repo / rel
        before = target.read_bytes()
        original = lifecycle.publish

        def replace_before_capture(fd, name, content, **kwargs):
            replacement = target.with_name("editor-save")
            replacement.write_bytes(b"concurrent editor content")
            replacement.replace(target)
            return original(fd, name, content, **kwargs)

        with (mock.patch.object(lifecycle, "publish", side_effect=replace_before_capture),
              self.assertRaises(OSError)):
            lifecycle.apply_uninstall(self.repo, {rel: before}, [(rel, before, None)], self.api)
        self.assertEqual(b"concurrent editor content", target.read_bytes())
        copies = list((self.repo / ".software-factory/backups").glob("uninstall-*/*.original"))
        self.assertTrue(any(p.read_bytes() == b"concurrent editor content" for p in copies))

    def test_new_destination_and_late_open_descriptor_writes_survive(self):
        self.install("cursor")
        rel = "AGENTS.md"
        target = self.repo / rel
        before = target.read_bytes()
        original_link = lifecycle.os.link
        editor = target.open("r+b")
        self.addCleanup(editor.close)
        injected = False

        def replace_before_publication(src, dst, **kwargs):
            nonlocal injected
            if not injected and src.endswith(".new"):
                injected = True
                target.write_bytes(b"new destination")
                editor.seek(0)
                editor.write(b"late descriptor edit")
                editor.truncate()
                editor.flush()
            return original_link(src, dst, **kwargs)

        with (mock.patch.object(lifecycle.os, "link", side_effect=replace_before_publication),
              self.assertRaises(OSError)):
            lifecycle.apply_uninstall(self.repo, {rel: before}, [(rel, before, b"replacement")], self.api)
        self.assertEqual(b"new destination", target.read_bytes())
        copies = list((self.repo / ".software-factory/backups").glob("uninstall-*/*.original"))
        self.assertTrue(any(p.read_bytes() == b"late descriptor edit" for p in copies))
        receipts = list((self.repo / ".software-factory/backups").glob("uninstall-*/*.json"))
        self.assertTrue(any(json.loads(p.read_text())["path"] == rel for p in receipts))

    def test_rollback_publication_never_clobbers_new_user_destination(self):
        self.install("cursor")
        rel = "AGENTS.md"
        target = self.repo / rel
        before = target.read_bytes()
        original_link = lifecycle.os.link
        publications = 0

        def interrupt_then_contest(src, dst, **kwargs):
            nonlocal publications
            if src.endswith(".new"):
                publications += 1
                if publications == 1:
                    original_link(src, dst, **kwargs)
                    raise KeyboardInterrupt()
                target.write_bytes(b"user edit during rollback")
            return original_link(src, dst, **kwargs)

        with (mock.patch.object(lifecycle.os, "link", side_effect=interrupt_then_contest),
              self.assertRaises(KeyboardInterrupt)):
            lifecycle.apply_uninstall(self.repo, {rel: before}, [(rel, before, b"replacement")], self.api)
        self.assertEqual(b"user edit during rollback", target.read_bytes())
        copies = list((self.repo / ".software-factory/backups").glob("uninstall-*/*.original"))
        self.assertTrue(any(p.read_bytes() == before for p in copies))

    def test_legacy_manifest_is_readable_but_unproven_restore_is_manual(self):
        self.install("cursor")
        path = self.repo / self.api.MANIFEST_REL
        data = self.manifest()
        for entry in data["files"]:
            entry.pop("restore", None)
        path.write_text(json.dumps(data))
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("provenance unverified", result.stdout)
        schema = json.loads((support.REPO / "schemas/installation.schema.json").read_text())
        properties = schema["properties"]["files"]["items"]
        self.assertIn("restore", properties["properties"])
        self.assertNotIn("restore", properties["required"])

    def test_waiting_writer_and_later_writer_share_persistent_lock_inode(self):
        self.install("cursor")
        lock_path = self.repo / self.api.LOCK_REL
        inode = lock_path.stat().st_ino
        _, observed, changes, _ = lifecycle.plan_uninstall(self.repo, ["cursor"], self.api)
        script = """import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDWR)
print("opened",flush=True)
fcntl.flock(fd,fcntl.LOCK_EX)
print("acquired",flush=True)
sys.stdin.readline()
fcntl.flock(fd,fcntl.LOCK_UN)
os.close(fd)
"""
        child = None
        original_write = lifecycle.publish

        def start_waiter(path, content, created, **kwargs):
            nonlocal child
            if child is None:
                child = subprocess.Popen([sys.executable, "-c", script, str(lock_path)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                self.addCleanup(lambda: child.poll() is None and child.kill())
                self.assertEqual("opened", child.stdout.readline().strip())
            return original_write(path, content, created, **kwargs)

        with mock.patch.object(lifecycle, "publish", side_effect=start_waiter):
            lifecycle.apply_uninstall(self.repo, observed, changes, self.api)
        self.assertIsNotNone(child)
        self.assertEqual("acquired", child.stdout.readline().strip())
        self.assertEqual(inode, lock_path.stat().st_ino)
        probe = subprocess.run(
            [sys.executable, "-c", (
                'import fcntl,os,sys\nf=os.open(sys.argv[1],os.O_RDWR)\n'
                'try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(23)\n'
            ), str(lock_path)], capture_output=True, check=False,
        )
        self.assertEqual(23, probe.returncode)
        child.stdin.write("release\n")
        child.stdin.flush()
        child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
        self.assertEqual(0, self.uninstall().returncode)
        self.assertEqual(inode, lock_path.stat().st_ino)


if __name__ == "__main__":
    unittest.main()
