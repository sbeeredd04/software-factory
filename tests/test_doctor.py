"""Read-only diagnostics, trusted fixture execution and sanitized reports."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sf_support", Path(__file__).with_name("support.py"))
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-doctor-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.repo = support.existing_repo(self.temp)
        self.env, self.guard, stub = support.guard_env()
        self.addCleanup(shutil.rmtree, stub, ignore_errors=True)
        self.gh = stub / "gh"
        self.gh.write_text('#!/bin/sh\nprintf "sensitive auth output\\n" >&2\nexit 0\n')
        self.gh.chmod(0o755)
        self.home, self.snapshot_home = support.home_sentinel(self.temp)
        self.env["HOME"] = str(self.home)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.home_before = self.snapshot_home()
        self.env.pop("CURSOR_VERSION", None)
        self.env.pop("CURSOR_PROJECT_DIR", None)

    def tearDown(self):
        self.assertFalse(self.guard.exists(), "host CLIs must never run")
        self.assertEqual(self.home_before, self.snapshot_home())

    def install(self, host="all", *args):
        result = support.run_installer("install", "--project", self.repo, "--host", host,
                                       "--skip-bmad", *args, env=self.env)
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def doctor(self, json_output=True):
        before = support.tree_hashes(self.repo)
        result = support.run_installer("doctor", "--project", self.repo,
                                       *(('--json',) if json_output else ()), env=self.env)
        self.assertEqual(before, support.tree_hashes(self.repo), "doctor changed the project")
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertNotIn("sensitive auth output", result.stdout + result.stderr)
        return result

    def checks(self):
        result = self.doctor()
        self.assertIn(result.returncode, (0, 1), result.stderr)
        data = json.loads(result.stdout)
        for check in data["checks"]:
            self.assertEqual({"name", "status", "detail"}, set(check))
            self.assertIn(check["status"], {"pass", "warning", "blocked", "unverified"})
        return result.returncode, {c["name"]: c for c in data["checks"]}

    def test_healthy_install_exercises_hooks_and_reports_truthful_limits(self):
        self.install()
        example = support.REPO / "examples/config"
        for item in example.iterdir():
            if item.name != "config.yaml":
                shutil.copy2(item, self.repo / item.name)
        config = json.loads((example / "config.yaml").read_text())
        config["project"]["root"] = ".."
        (self.repo / ".software-factory/config.yaml").write_text(json.dumps(config))
        code, checks = self.checks()
        self.assertEqual(0, code)
        for host in ("claude-code", "cursor", "codex"):
            self.assertEqual("pass", checks[f"hooks:{host}"]["status"])
            self.assertIn("disposable", checks[f"hooks:{host}"]["detail"])
        self.assertEqual("pass", checks["config-syntax"]["status"])
        self.assertEqual("pass", checks["config-semantics"]["status"])
        self.assertEqual("unverified", checks["codex-hook-trust"]["status"])
        self.assertIn("/hooks", checks["codex-hook-trust"]["detail"])
        self.assertIn("user-confirmation-required", checks["codex-hook-trust"]["detail"])
        self.assertEqual("warning", checks["codex-agent-permissions"]["status"])
        self.assertEqual("unverified", checks["global-plugin-state"]["status"])
        self.assertEqual("unverified", checks["shared-skill-loading"]["status"])
        self.assertEqual("warning", checks["ambient-skill-sources"]["status"])
        self.assertEqual("pass", checks["github-auth"]["status"])
        text = self.doctor(False)
        self.assertEqual(0, text.returncode)
        for check in checks.values():
            self.assertIn(check["name"], text.stdout)

    def test_missing_installation_has_repair_instruction_and_no_writes(self):
        code, checks = self.checks()
        self.assertEqual(1, code)
        self.assertEqual("blocked", checks["installation"]["status"])
        self.assertIn("install.py install", checks["installation"]["detail"])
        self.assertFalse((self.repo / ".software-factory").exists())

    def test_drift_and_corrupt_state_degrade_without_refreshing_actual_run(self):
        self.install()
        pointer = self.repo / ".software-factory/active.json"
        pointer.write_text('{"broken-private-value": tru')
        _, checks = self.checks()
        self.assertEqual("warning", checks["recovery-state"]["status"])
        self.assertNotIn("broken-private-value", json.dumps(checks))
        runtime = self.repo / ".software-factory/runtime/hook.py"
        runtime.write_text('raise RuntimeError("private runtime content")\n')
        _, checks = self.checks()
        for host in ("claude-code", "cursor", "codex"):
            self.assertEqual("warning", checks[f"hooks:{host}"]["status"])
        self.assertNotIn("private runtime content", json.dumps(checks))

    def test_moved_checkout_warns_without_executing_stale_paths(self):
        self.install()
        moved = self.temp / "moved repo"
        shutil.copytree(self.repo, moved)
        original = support.tree_hashes(self.repo)
        self.repo = moved
        code, checks = self.checks()
        self.assertEqual(0, code)
        for host in ("claude-code", "cursor", "codex"):
            self.assertEqual("warning", checks[f"hooks:{host}"]["status"])
        self.assertEqual(original, support.tree_hashes(self.temp / "repo"))

    def test_adversarial_commands_and_forged_runtime_hash_never_execute(self):
        self.install()
        marker = self.temp / "must-not-run"
        hooks = self.repo / ".cursor/hooks.json"
        doc = json.loads(hooks.read_text())
        doc["hooks"]["sessionStart"][0]["command"] = f'touch "{marker}"'
        hooks.write_text(json.dumps(doc))
        runtime = self.repo / ".software-factory/runtime/hook.py"
        runtime.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        manifest = self.repo / ".software-factory/installation.json"
        data = json.loads(manifest.read_text())
        for entry in data["files"]:
            if entry["path"] == ".software-factory/runtime/hook.py":
                entry["sha256"] = hashlib.sha256(runtime.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data))
        _, checks = self.checks()
        self.assertFalse(marker.exists())
        self.assertEqual("warning", checks["hooks:cursor"]["status"])
        self.assertEqual("warning", checks["hooks:claude-code"]["status"])

    def test_bypasses_block_and_diagnostic_values_are_redacted(self):
        self.install("claude-code")
        path = self.repo / ".claude/settings.json"
        doc = json.loads(path.read_text())
        doc["permissions"]["defaultMode"] = "bypassPermissions"
        doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = (
            "echo PRIVATE-VALUE --dangerously-skip-permissions"
        )
        path.write_text(json.dumps(doc))
        code, checks = self.checks()
        self.assertEqual(1, code)
        blocked = [c for c in checks.values() if c["status"] == "blocked"]
        self.assertTrue(any("bypassPermissions" in c["detail"] for c in blocked))
        self.assertTrue(any("--dangerously-skip-permissions" in c["detail"] for c in blocked))
        self.assertNotIn("PRIVATE-VALUE", json.dumps(checks))
        self.assertNotIn("codex-hook-trust", checks)
        self.assertNotIn("ambient-skill-sources", checks)

    def test_invalid_config_never_partially_affects_other_checks(self):
        self.install("cursor")
        path = self.repo / ".software-factory/config.yaml"
        path.write_text('{}')
        _, before = self.checks()
        path.write_text('bad: [1,2\n')
        code, after = self.checks()
        self.assertEqual(1, code)
        self.assertEqual("blocked", after["config-syntax"]["status"])
        self.assertIn("JSON-compatible YAML", after["config-syntax"]["detail"])
        before.pop("config-semantics")
        after.pop("config-semantics")
        before.pop("config-syntax")
        after.pop("config-syntax")
        # Board path interpretation also depends on a fully parsed config.
        self.assertIn("unreadable", after["board-records"]["detail"])
        before.pop("board-records")
        after.pop("board-records")
        self.assertEqual(before, after)

    def test_missing_gh_and_unsafe_manifest_are_reported_without_crashing(self):
        self.install("cursor")
        self.env["PATH"] = str(self.gh.parent)
        self.gh.unlink()
        _, checks = self.checks()
        self.assertEqual("warning", checks["github-auth"]["status"])
        path = self.repo / ".software-factory/installation.json"
        data = json.loads(path.read_text())
        data["files"][0]["path"] = "../../PRIVATE-VALUE"
        path.write_text(json.dumps(data))
        code, checks = self.checks()
        self.assertEqual(1, code)
        self.assertEqual("blocked", checks["installation"]["status"])
        self.assertNotIn("PRIVATE-VALUE", json.dumps(checks))

    def test_real_active_state_is_unchanged_by_disposable_hook_proof(self):
        self.install("codex")
        run = self.repo / ".software-factory/runs/demo/run.json"
        run.parent.mkdir(parents=True)
        run.write_text(json.dumps({
            "version": 1, "program": "demo", "tracker": "tracker.yaml",
            "principles": "principles.md", "claims": {}, "checkpoint": {}, "revision": 7,
        }))
        (self.repo / ".software-factory/active.json").write_text(json.dumps({
            "version": 1, "run": ".software-factory/runs/demo/run.json",
        }))
        (self.repo / "principles.md").write_text("User-authored principles")
        (self.repo / "tracker.yaml").write_text("{}")
        code, checks = self.checks()
        self.assertEqual(0, code)
        self.assertEqual("pass", checks["hooks:codex"]["status"])
        self.assertEqual(7, json.loads(run.read_text())["revision"])
        self.assertFalse(run.with_name("CHECKPOINT.md").exists())

    def test_missing_and_empty_active_principles_block_without_fallback(self):
        self.test_real_active_state_is_unchanged_by_disposable_hook_proof()
        path = self.repo / "principles.md"
        for content in (None, "", " \n"):
            if content is None:
                path.unlink()
            else:
                path.write_text(content)
            code, checks = self.checks()
            self.assertEqual(1, code)
            self.assertEqual("blocked", checks["principles"]["status"])
            self.assertIn("principles.md", checks["principles"]["detail"])
            self.assertIn("no fallback", checks["principles"]["detail"])
        path.write_text("User-authored principles")
        (self.repo / "tracker.yaml").unlink()
        code, checks = self.checks()
        self.assertEqual(1, code)
        self.assertEqual("blocked", checks["tracker"]["status"])

    def test_board_status_authority_missing_and_stale_projections_are_observed(self):
        self.install("cursor")
        source = self.repo / "plan.json"
        source.write_text(json.dumps({
            "streams": [{"id": "W-core", "title": "Core", "status": "active"}],
            "epics": [{"key": "core", "stream": "W-core", "title": "Core",
                       "outcome": "Reliable behavior", "done_when": ["Proof"],
                       "covers": [], "needs": [], "stories": [
                           {"key": "first", "title": "First", "after": [], "covers": []}]}],
        }))
        result = subprocess.run([sys.executable, str(support.SCRIPTS / "roadmap.py"),
                                 "derive", "--workspace", str(self.repo), "--source", str(source)],
                                env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        board = self.repo / ".software-factory/context/board"
        _, checks = self.checks()
        self.assertEqual("pass", checks["board-roadmap"]["status"])
        self.assertEqual("pass", checks["board-dashboard"]["status"])
        story_path = board / "stories/1.json"
        story = json.loads(story_path.read_text())
        story["status"] = "ready-for-dev"
        story_path.write_text(json.dumps(story))
        (self.repo / ".software-factory/board.lock").unlink(missing_ok=True)
        (self.repo / ".software-factory/state.lock").unlink(missing_ok=True)
        _, checks = self.checks()
        self.assertEqual("pass", checks["board-records"]["status"])
        self.assertEqual("warning", checks["board-roadmap"]["status"])
        self.assertEqual("warning", checks["board-dashboard"]["status"])
        for rel in ("roadmap.json", "dashboard.html"):
            (board / rel).unlink()
        _, checks = self.checks()
        self.assertEqual("warning", checks["board-roadmap"]["status"])
        self.assertEqual("warning", checks["board-dashboard"]["status"])
        self.assertFalse((self.repo / ".software-factory/board.lock").exists())
        self.assertFalse((self.repo / ".software-factory/state.lock").exists())

    def test_run_audit_reports_layout_budget_binary_without_sensitive_names(self):
        self.install("cursor")
        run = self.repo / ".software-factory/runs/demo"
        run.mkdir(parents=True)
        (run / "PRIVATE-VALUE.dat").write_bytes(b"\x00" + b"a" * (1024 * 1024))
        _, checks = self.checks()
        self.assertEqual("warning", checks["runs-audit"]["status"])
        for category in ("layout", "size budget", "binary"):
            self.assertIn(category, checks["runs-audit"]["detail"])
        self.assertNotIn("PRIVATE-VALUE", json.dumps(checks))

    def test_fresh_pack_and_project_remain_read_only_without_bytecode_or_locks(self):
        self.install("cursor")
        copied = self.temp / "fresh-pack"
        shutil.copytree(support.REPO, copied,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        before_pack = support.tree_hashes(copied)
        before_project = support.tree_hashes(self.repo)
        env = {**self.env}
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run([sys.executable, str(copied / "install.py"), "doctor",
                                 "--project", str(self.repo), "--json"],
                                env=env, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before_pack, support.tree_hashes(copied))
        self.assertEqual(before_project, support.tree_hashes(self.repo))
        self.assertEqual([], list(copied.rglob("__pycache__")))

    def test_backup_drift_and_inherited_agent_sandbox_are_not_reported_as_pass(self):
        self.install("codex")
        manifest = json.loads((self.repo / ".software-factory/installation.json").read_text())
        entry = next(e for e in manifest["files"] if e["path"] == "AGENTS.md")
        (self.repo / entry["restore"]["path"]).write_text("changed backup")
        agent = self.repo / ".codex/agents/sf-code-reviewer.toml"
        agent.write_text(agent.read_text() + '\nsandbox_mode = "read-only"\n')
        _, checks = self.checks()
        self.assertEqual("warning", checks["backup:AGENTS.md"]["status"])
        self.assertEqual("warning", checks["codex-agent-permissions"]["status"])
        self.assertIn("do not enforce", checks["codex-agent-permissions"]["detail"])

    def test_symlinked_runtime_is_never_executed(self):
        self.install()
        runtime = self.repo / ".software-factory/runtime/hook.py"
        external = self.temp / "external.py"
        external.write_text('raise RuntimeError("do not execute")')
        runtime.unlink()
        runtime.symlink_to(external)
        code, checks = self.checks()
        self.assertEqual(1, code)
        self.assertEqual("blocked", checks["installation"]["status"])
        self.assertNotIn("do not execute", json.dumps(checks))


if __name__ == "__main__":
    unittest.main()
