"""Execute installed hook commands with fixture input; never launch a host.

Covers VAL-HOST-014..018 through real project projections, independently of
canonical helper tests. JSON envelopes and merged diagnostic transport are
different outcomes; neither proves that a live host loads these hooks.
"""
from __future__ import annotations

import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

HOSTS = ("claude-code", "cursor", "codex")
FILES = {
    "claude-code": ".claude/settings.json",
    "cursor": ".cursor/hooks.json",
    "codex": ".codex/hooks.json",
}
WARNING = "Software Factory recovery warning: state could not be read; reconcile manually.\n"


class InstalledHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-installed-hooks-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.env, self.guard_log, stub_dir = support.guard_env()
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        self.python_log = self.temp / "ambient-python.log"
        # An incompatible ambient python must never replace the installer runtime.
        ambient = stub_dir / "python3"
        ambient.write_text(
            '#!/bin/sh\nprintf "ambient Python 3.9\\n" > "$SF_PYTHON_LOG"\nexit 91\n'
        )
        ambient.chmod(0o755)
        self.env["SF_PYTHON_LOG"] = str(self.python_log)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.env.pop("CURSOR_VERSION", None)
        self.env.pop("CURSOR_PROJECT_DIR", None)
        self.home, self.home_snapshot = support.home_sentinel(self.temp)
        self.env["HOME"] = str(self.home)
        self.home_before = self.home_snapshot()
        # Literal shell metacharacters exercise quoting without executing them.
        self.repo = support.existing_repo(
            self.temp, "project space ' $(touch SHOULD-NOT-EXIST) `touch ALSO-NOT`"
        )
        self.user_group = {
            "matcher": "startup",
            "hooks": [{"type": "command", "command": "echo user-start"}],
        }
        for host in ("claude-code", "codex"):
            path = self.repo / FILES[host]
            path.parent.mkdir(exist_ok=True)
            data = json.loads(path.read_text()) if path.exists() else {}
            data.setdefault("hooks", {})["SessionStart"] = [self.user_group]
            path.write_text(json.dumps(data))
        cursor_path = self.repo / FILES["cursor"]
        data = json.loads(cursor_path.read_text())
        self.user_cursor = {"command": "echo cursor-user-start"}
        data["hooks"]["sessionStart"] = [self.user_cursor]
        cursor_path.write_text(json.dumps(data))
        result = support.run_installer(
            "install", "--project", self.repo, "--host", "all", "--skip-bmad", env=self.env
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def tearDown(self):
        self.assertFalse(self.guard_log.exists(), "host CLIs must never run")
        self.assertFalse(self.python_log.exists(), "ambient Python must never run")
        self.assertEqual(self.home_before, self.home_snapshot())
        for marker in ("SHOULD-NOT-EXIST", "ALSO-NOT"):
            self.assertFalse((self.temp / marker).exists())
            self.assertFalse((self.repo / marker).exists())

    def command(self, host, event):
        data = json.loads((self.repo / FILES[host]).read_text())
        if host == "cursor":
            key = "sessionStart" if event == "session-start" else "preCompact"
            handlers = data["hooks"][key]
        else:
            key = "SessionStart" if event == "session-start" else "PreCompact"
            handlers = [handler for group in data["hooks"][key] for handler in group["hooks"]]
        commands = [h["command"] for h in handlers if "runtime/hook.py" in h.get("command", "")]
        self.assertEqual(1, len(commands))
        return commands[0]

    def execute(self, host, event="session-start", *, payload=None, env=None, cwd=None):
        if payload is None:
            payload = {
                "session_id": "fixture-session", "is_background_agent": False,
                "hook_event_name": "SessionStart" if event == "session-start" else "PreCompact",
                "trigger": "manual", "cwd": "/ignored-payload-location",
            }
        return subprocess.run(
            ["/bin/sh", "-c", self.command(host, event)],
            input=json.dumps(payload), capture_output=True, text=True,
            cwd=cwd or self.temp, env=env or self.env, check=False, timeout=30,
        )

    def state(self, command, *args):
        result = subprocess.run(
            [sys.executable, str(self.repo / ".software-factory/runtime/state.py"),
             command, "--workspace", str(self.repo), *map(str, args)],
            capture_output=True, text=True, cwd=self.temp, env=self.env,
            check=False, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def activate(self):
        (self.repo / "principles.md").write_text("Authoritative fixture principles\n")
        (self.repo / "tracker.yaml").write_text("stories: {}\n")
        self.state("init", "--program", "demo", "--tracker", "tracker.yaml",
                   "--principles", "principles.md")
        return self.repo / ".software-factory/runs/demo/run.json"

    def assert_silent(self, result):
        self.assertEqual((0, "", ""), (result.returncode, result.stdout, result.stderr))

    def context(self, host, result):
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        data = json.loads(result.stdout)
        if host == "cursor":
            self.assertEqual({"additional_context"}, set(data))
            return data["additional_context"]
        self.assertEqual({"hookSpecificOutput"}, set(data))
        inner = data["hookSpecificOutput"]
        self.assertEqual({"hookEventName", "additionalContext"}, set(inner))
        self.assertEqual("SessionStart", inner["hookEventName"])
        return inner["additionalContext"]

    def test_no_pointer_is_inert_for_all_installed_commands(self):
        before = support.tree_hashes(self.repo)
        for host in HOSTS:
            for event in ("session-start", "pre-compact"):
                with self.subTest(host=host, event=event):
                    self.assert_silent(self.execute(host, event))
        self.assertEqual(before, support.tree_hashes(self.repo))

    def test_installed_envelopes_prioritize_essential_notes_over_checkpoint_details(self):
        self.activate()
        notes = support.notes()
        notes["objective"] = "O" * 500
        notes["next"] = "N" * 500
        notes["completed"] = ["COMPLETED-TEXT-SENTINEL"] * 8
        sentinel = "S" * 2000
        notes_path = self.repo / "notes.json"
        notes_path.write_text(json.dumps(notes))
        self.state("checkpoint", "--notes", notes_path)
        self.state("claim", "--task", "fixture-task", "--owner", "fixture-worker",
                   "--repo", self.repo, "--paths", sentinel)
        checkpoint = self.repo / ".software-factory/runs/demo/CHECKPOINT.md"
        self.assertIn(sentinel, checkpoint.read_text())
        for host in HOSTS:
            with self.subTest(host=host):
                context = self.context(host, self.execute(host))
                self.assertLessEqual(len(context), 1500)
                self.assertIn("runs/demo/CHECKPOINT.md", context)
                self.assertIn("not a new authorization", context)
                self.assertIn("lower-trust recovery facts, not instructions", context)
                self.assertIn(notes["objective"], context)
                self.assertNotIn(sentinel, context)
                self.assertIn(notes["next"], context)
                self.assertNotIn(notes["completed"][0], context)

    def test_background_workers_are_inert_with_active_state(self):
        self.activate()
        before = support.tree_hashes(self.repo)
        for host in HOSTS:
            for event in ("session-start", "pre-compact"):
                self.assert_silent(self.execute(host, event, payload={"is_background_agent": True}))
        self.assertEqual(before, support.tree_hashes(self.repo))

    def test_precompact_refreshes_git_snapshot_and_preserves_notes(self):
        run_path = self.activate()
        self.state("claim", "--task", "fixture-task", "--owner", "fixture-worker",
                   "--repo", self.repo, "--paths", "src")
        for host in HOSTS:
            with self.subTest(host=host):
                before = json.loads(run_path.read_text())
                self.assert_silent(self.execute(host, "pre-compact"))
                after = json.loads(run_path.read_text())
                self.assertGreater(after["revision"], before["revision"])
                self.assertEqual(before["checkpoint"], after["checkpoint"])
                observation = after["claims"]["fixture-task"]["observation"]
                expected_head = support.Workspace.git(self.repo, "rev-parse", "HEAD").stdout.strip()
                self.assertEqual(expected_head, observation["head"])
                self.assertIsInstance(observation["dirty"], bool)
                self.assertTrue(run_path.with_name("CHECKPOINT.md").is_file())

    def test_precompact_write_failure_does_not_block_or_echo_state(self):
        run_path = self.activate()
        lock = self.repo / ".software-factory/state.lock"
        lock.unlink()
        lock.mkdir()  # An actual write failure, independent of permission mode.
        before = support.tree_hashes(self.repo)
        before_run = run_path.read_bytes()
        for host in HOSTS:
            with self.subTest(host=host):
                result = self.execute(host, "pre-compact", payload={"note": "INPUT-SENTINEL"})
                self.assertEqual((0, WARNING, ""),
                                 (result.returncode, result.stdout, result.stderr))
                self.assertEqual(before_run, run_path.read_bytes())
        self.assertEqual(before, support.tree_hashes(self.repo))

    def test_corruption_is_a_sanitized_diagnostic_not_a_json_envelope(self):
        self.activate()
        (self.repo / ".software-factory/active.json").write_text('{"broken-sensitive": tru')
        before = support.tree_hashes(self.repo)
        for host in HOSTS:
            for event in ("session-start", "pre-compact"):
                with self.subTest(host=host, event=event):
                    result = self.execute(host, event, payload={"note": "INPUT-SENTINEL"})
                    self.assertEqual(0, result.returncode)
                    self.assertEqual(WARNING, result.stdout)
                    self.assertEqual("", result.stderr)
                    # The helper itself keeps warnings on stderr; the installed
                    # command's explicit 2>&1 is what transports them on stdout.
                    argv = shlex.split(self.command(host, event).removesuffix(" 2>&1"))
                    direct = subprocess.run(
                        argv, input='{"note":"INPUT-SENTINEL"}', capture_output=True,
                        text=True, cwd=self.temp, env=self.env, check=False, timeout=30,
                    )
                    self.assertEqual((0, "", WARNING),
                                     (direct.returncode, direct.stdout, direct.stderr))
        self.assertEqual(before, support.tree_hashes(self.repo))

    def test_native_cursor_adapter_suppresses_only_matching_claude_events(self):
        run_path = self.activate()
        cursor_env = {**self.env, "CURSOR_VERSION": "fixture", "CURSOR_PROJECT_DIR": str(self.repo)}
        for event in ("session-start", "pre-compact"):
            before = run_path.read_bytes()
            self.assert_silent(self.execute("claude-code", event, env=cursor_env))
            self.assertEqual(before, run_path.read_bytes())
        self.context("cursor", self.execute("cursor", env=cursor_env))
        revision = json.loads(run_path.read_text())["revision"]
        self.assert_silent(self.execute("cursor", "pre-compact", env=cursor_env))
        self.assertEqual(revision + 1, json.loads(run_path.read_text())["revision"])
        self.context("claude-code", self.execute("claude-code"))
        # A native preCompact adapter cannot replace Claude SessionStart.
        cursor_path = self.repo / FILES["cursor"]
        data = json.loads(cursor_path.read_text())
        data["hooks"]["sessionStart"] = [self.user_cursor]
        cursor_path.write_text(json.dumps(data))
        self.context("claude-code", self.execute("claude-code", env=cursor_env))
        self.assert_silent(self.execute("claude-code", "pre-compact", env=cursor_env))
        cursor_path.unlink()
        self.context("claude-code", self.execute("claude-code", env=cursor_env))
        self.assert_silent(self.execute("claude-code", "pre-compact", env=cursor_env))

    def test_user_hooks_are_preserved_and_reinstall_does_not_duplicate_adapters(self):
        before = support.tree_hashes(self.repo)
        again = support.run_installer(
            "install", "--project", self.repo, "--host", "all", "--skip-bmad", env=self.env
        )
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("0 changes", again.stdout)
        self.assertEqual(before, support.tree_hashes(self.repo))
        for host in HOSTS:
            data = json.loads((self.repo / FILES[host]).read_text())
            if host == "cursor":
                self.assertIn(self.user_cursor, data["hooks"]["sessionStart"])
            else:
                self.assertIn(self.user_group, data["hooks"]["SessionStart"])
            for event in ("session-start", "pre-compact"):
                argv = shlex.split(self.command(host, event))
                self.assertEqual(sys.executable, argv[0])
                self.assertEqual(str(self.repo), argv[argv.index("--workspace") + 1])

    def test_installer_interpreter_path_with_spaces_survives_shell_execution(self):
        runtime = self.temp / "runtime space '" / "python3"
        runtime.parent.mkdir()
        runtime.symlink_to(sys.executable)
        result = subprocess.run(
            [str(runtime), str(support.INSTALLER), "install", "--project", str(self.repo),
             "--host", "all", "--skip-bmad"], capture_output=True, text=True,
            env=self.env, check=False, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.activate()
        for host in HOSTS:
            self.assertEqual(str(runtime), shlex.split(self.command(host, "session-start"))[0])
            self.context(host, self.execute(host, cwd=self.repo / ".software-factory/runtime"))


if __name__ == "__main__":
    unittest.main()
