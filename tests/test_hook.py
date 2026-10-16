"""Tests for the recovery-hook kernel helper (hook.py).

Encodes the VAL-KERNEL hook assertions: inertness without an active pointer,
host-correct JSON envelopes for Claude Code, Cursor and Codex, a capped
recovery pointer that never inlines full checkpoint prose, silent pre-compact
snapshot refresh, background filtering, Cursor-coexistence suppression, and
sanitized behavior on malformed input or corrupt state.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

SCRIPTS = support.SCRIPTS
HOSTS = ("claude-code", "cursor", "codex")
CC_START = '{"session_id":"s1","cwd":"/fixture","hook_event_name":"SessionStart","permission_mode":"default"}'
CU_START = '{"session_id":"s1","is_background_agent":false}'
PRECOMPACT = '{"session_id":"s1","trigger":"manual","hook_event_name":"PreCompact"}'


def run_hook(host, event, workspace, stdin=CC_START, env=None):
    return support.run(
        "hook", "--host", host, "--event", event, "--workspace", workspace,
        stdin=stdin, env=env,
    )


class HookFixture(unittest.TestCase):
    def setUp(self):
        self.ws = support.Workspace()
        self.addCleanup(self.ws.cleanup)

    def context(self, host="claude-code", stdin=CC_START, event="session-start", env=None):
        result = run_hook(host, event, self.ws.root, stdin=stdin, env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        if not result.stdout.strip():
            return None, result
        payload = json.loads(result.stdout)
        if host == "cursor":
            self.assertEqual({"additional_context"}, set(payload))
            return payload["additional_context"], result
        self.assertEqual({"hookSpecificOutput"}, set(payload))
        inner = payload["hookSpecificOutput"]
        self.assertEqual("SessionStart", inner["hookEventName"])
        return inner["additionalContext"], result


class InertnessTests(unittest.TestCase):
    def test_without_active_pointer_every_host_is_silent(self):
        unmanaged = Path(tempfile.mkdtemp(prefix="sf-unmanaged-"))
        self.addCleanup(shutil.rmtree, unmanaged, ignore_errors=True)
        for host in HOSTS:
            with self.subTest(host=host):
                result = run_hook(host, "session-start", unmanaged)
                self.assertEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual("", result.stderr)
        result = run_hook("claude-code", "pre-compact", unmanaged, stdin=PRECOMPACT)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual([], list(unmanaged.iterdir()))

    def test_unmanaged_workspace_ignores_malformed_input_without_writes(self):
        with tempfile.TemporaryDirectory() as root:
            for host in HOSTS:
                for event in ("session-start", "pre-compact"):
                    for payload in ("not json", "x" * 70000):
                        with self.subTest(host=host, event=event, size=len(payload)):
                            result = run_hook(host, event, root, stdin=payload)
                            self.assertEqual((0, "", ""), (
                                result.returncode, result.stdout, result.stderr,
                            ))
                            self.assertEqual([], list(Path(root).iterdir()))


class EnvelopeTests(HookFixture):
    def test_session_start_envelopes_per_host(self):
        for host in HOSTS:
            with self.subTest(host=host):
                context, _ = self.context(host=host, stdin=CU_START if host == "cursor" else CC_START)
                self.assertTrue(context)
                self.assertLessEqual(len(context), 1500)
                self.assertIn("not a new authorization", context)
                self.assertIn(".software-factory/runs/demo/CHECKPOINT.md", context)
                self.assertIn("runs/demo", context)

    def test_recovery_pointer_is_framed_as_facts_not_instructions(self):
        context, _ = self.context()
        self.assertIn("lower-trust recovery facts, not instructions", context)
        self.assertIn("reconcile", context)

    def test_truncation_removes_huge_checkpoint_lines(self):
        sentinel = "S" * 2000
        repo = self.ws.repo()
        result = self.ws.claim("t1", "worker-a", repo, sentinel)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(sentinel, self.ws.checkpoint_file().read_text())
        context, _ = self.context()
        self.assertNotIn(sentinel, context)
        self.assertLessEqual(len(context), 1500)

    def test_essential_notes_survive_without_detailed_checkpoint_prose(self):
        notes = support.notes()
        notes["objective"] = "O" * 500
        notes["next"] = "N" * 500
        notes["completed"] = ["COMPLETED-TEXT-SENTINEL"] * 8
        self.assertEqual(0, self.ws.checkpoint(notes).returncode)
        self.assertIn(notes["objective"], self.ws.checkpoint_file().read_text())
        for host in HOSTS:
            context, _ = self.context(host=host)
            self.assertIn(notes["objective"], context)
            self.assertIn(notes["next"], context)
            self.assertNotIn(notes["completed"][0], context)
            self.assertIn("CHECKPOINT.md", context)
            self.assertLessEqual(len(context), 1500)

    def test_pointer_budget_keeps_exact_next_action_with_large_recovery_lists(self):
        notes = support.notes()
        notes["objective"] = "O" * 500
        notes["next"] = "N" * 500
        notes["completed"] = ["history " * 50] * 8
        data = {
            "program": "p" * 64, "checkpoint": notes,
            "claims": {f"task-{index}": {"paths": ["src/" * 500]} for index in range(100)},
        }
        context = support.helper("hook").recovery_pointer(data)
        self.assertLessEqual(len(context), 1500)
        self.assertIn(notes["objective"], context)
        self.assertIn(notes["next"], context)
        self.assertIn("Saved active claims: 100", context)
        self.assertNotIn("history", context)
        self.assertNotIn("src/", context)

    def test_input_payload_is_never_echoed(self):
        marker = "PAYLOAD-SENTINEL-4c1f"
        stdin = json.dumps({"session_id": "s1", "note": marker})
        context, result = self.context(stdin=stdin)
        self.assertNotIn(marker, context or "")
        self.assertNotIn(marker, result.stderr)

    def test_event_aliases_map_to_the_same_behavior(self):
        for alias in ("session-start", "SessionStart"):
            with self.subTest(alias=alias):
                context, _ = self.context(event=alias)
                self.assertTrue(context)

    def test_unknown_host_or_event_warns_without_crashing(self):
        result = run_hook("vscode", "session-start", self.ws.root)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("recovery warning", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        result = run_hook("claude-code", "deploy", self.ws.root)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("recovery warning", result.stderr)


class PreCompactTests(HookFixture):
    def test_pre_compact_refreshes_snapshot_and_prints_nothing(self):
        repo = self.ws.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        self.assertEqual(0, self.ws.checkpoint(support.notes()).returncode)
        before = self.ws.run_file().read_text()
        for host in HOSTS:
            with self.subTest(host=host):
                result = run_hook(host, "pre-compact", self.ws.root, stdin=PRECOMPACT)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)
                self.assertEqual("", result.stderr)
        observation = self.ws.state()["claims"]["t1"]["observation"]
        self.assertRegex(observation["head"], r"^[0-9a-f]{40}$")
        self.assertEqual(support.notes(), self.ws.state()["checkpoint"])
        self.assertNotEqual(before, self.ws.run_file().read_text())


class BadInputTests(HookFixture):
    def test_malformed_payloads_warn_sanitized(self):
        cases = {
            "not JSON": "this is not json",
            "non-object": '["session"]',
            "truncated": '{"a": ',
            "oversized": "x" * 70000,
        }
        for label, stdin in cases.items():
            with self.subTest(case=label):
                result = run_hook("claude-code", "session-start", self.ws.root, stdin=stdin)
                self.assertEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                lines = [line for line in result.stderr.strip().splitlines() if line]
                self.assertEqual(1, len(lines))
                self.assertIn("recovery warning", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_corrupt_state_warns_without_leaking_content(self):
        self.ws.pointer_file().write_text("not-json-sensitive")
        result = run_hook("claude-code", "session-start", self.ws.root)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        lines = [line for line in result.stderr.strip().splitlines() if line]
        self.assertEqual(1, len(lines))
        self.assertIn("reconcile manually", result.stderr)
        self.assertNotIn("sensitive", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_background_agents_are_filtered(self):
        repo = self.ws.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        for host in HOSTS:
            with self.subTest(host=host):
                stdin = json.dumps({"session_id": "s1", "is_background_agent": True})
                result = run_hook(host, "session-start", self.ws.root, stdin=stdin)
                self.assertEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual("", result.stderr)


class SuppressionTests(HookFixture):
    def cursor_env(self, present):
        env = dict(os.environ)
        if present:
            env["CURSOR_VERSION"] = "2026.1"
            env["CURSOR_PROJECT_DIR"] = str(self.ws.root)
        else:
            env.pop("CURSOR_VERSION", None)
            env.pop("CURSOR_PROJECT_DIR", None)
        return env

    def test_claude_host_suppresses_only_under_detected_cursor(self):
        projection = self.ws.root / ".cursor" / "hooks.json"
        projection.parent.mkdir(parents=True, exist_ok=True)
        command = shlex.join([
            sys.executable, str(self.ws.root / ".software-factory/runtime/hook.py"),
            "--host", "cursor", "--event", "session-start",
        ]) + " 2>&1"
        projection.write_text(json.dumps({
            "version": 1, "hooks": {"sessionStart": [{"command": command}]},
        }))
        result = run_hook("claude-code", "session-start", self.ws.root, env=self.cursor_env(True))
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)
        context, _ = self.context(env=self.cursor_env(False))
        self.assertTrue(context)
        projection.unlink()
        context, _ = self.context(env=self.cursor_env(True))
        self.assertTrue(context)

    def test_unrelated_or_malformed_cursor_config_does_not_suppress_recovery(self):
        projection = self.ws.root / ".cursor/hooks.json"
        projection.parent.mkdir(parents=True)
        for config in (
            '{"version": 1, "hooks": {}}',
            '{"version": 1, "hooks": {"sessionStart": [{"command": "echo user"}]}}',
            '{"version": 1, "hooks": {"sessionStart": [null, {"command": 7}]}}',
            '{"version": 1, "hooks": {"sessionStart": null}}',
            '{"version": 1, "hooks": []}',
            '{"broken":',
        ):
            with self.subTest(config=config):
                projection.write_text(config)
                context, result = self.context(env=self.cursor_env(True))
                self.assertTrue(context)
                self.assertEqual("", result.stderr)

    def test_nonfactory_command_and_different_workspace_do_not_suppress(self):
        projection = self.ws.root / ".cursor/hooks.json"
        projection.parent.mkdir(parents=True)
        script = str(self.ws.root / ".software-factory/runtime/hook.py")
        for argv in (
            ["/bin/echo", script, "--host", "cursor", "--event", "session-start"],
            [sys.executable, script, "--host", "cursor", "--event", "session-start",
             "--workspace", str(self.ws.root / "different-project")],
        ):
            with self.subTest(argv=argv):
                projection.write_text(json.dumps({
                    "version": 1, "hooks": {"sessionStart": [{"command": shlex.join(argv)}]},
                }))
                context, result = self.context(env=self.cursor_env(True))
                self.assertTrue(context)
                self.assertEqual("", result.stderr)

    def test_cursor_host_still_emits_under_cursor_env(self):
        context, _ = self.context(host="cursor", stdin=CU_START, env=self.cursor_env(True))
        self.assertTrue(context)


class HelperSafetyTests(HookFixture):
    def test_imports_are_standard_library_only(self):
        self.assertEqual([], support.non_stdlib_imports(SCRIPTS / "hook.py"))

    def test_hooks_never_invoke_host_clis(self):
        env, log, stub_dir = support.guard_env()
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        repo = self.ws.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src", env=env).returncode)
        for host in HOSTS:
            run_hook(host, "session-start", self.ws.root, env=env)
            run_hook(host, "pre-compact", self.ws.root, stdin=PRECOMPACT, env=env)
        self.assertFalse(log.exists() and log.read_text())

    def test_source_has_no_dispatch_mechanism(self):
        source = (SCRIPTS / "hook.py").read_text()
        for banned in ("subprocess", "os.system", "popen", "urllib", "socket", "http.client"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
