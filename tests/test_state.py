"""Tests for the execution-state kernel helper (state.py).

Encodes the VAL-KERNEL state assertions: neutral run paths, idempotent init,
claim scope validation, worktree identity collisions, concurrency, checkpoint
shape limits, credential refusal, degraded Git observation, read-only status,
deactivate/repair ownership, and atomic lock-protected writes.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

state = support.helper("state")
SCRIPTS = support.SCRIPTS


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class StateFixture(unittest.TestCase):
    def setUp(self):
        self.ws = support.Workspace()
        self.addCleanup(self.ws.cleanup)

    def repo(self, name="repo"):
        return self.ws.repo(name)


class InitTests(StateFixture):
    def test_init_uses_neutral_run_paths(self):
        pointer = json.loads(self.ws.pointer_file().read_text())
        self.assertEqual(
            {"version": 1, "run": ".software-factory/runs/demo/run.json"}, pointer
        )
        self.assertTrue(self.ws.run_file().is_file())
        self.assertTrue(self.ws.checkpoint_file().is_file())
        home = self.ws.root / ".software-factory"
        sources = {self.ws.root / "principles.md", self.ws.root / "tracker.yaml"}
        created = {item for item in self.ws.root.rglob("*") if item not in sources}
        self.assertTrue(created)
        self.assertTrue(all(item.is_relative_to(home) for item in created), sorted(map(str, created)))

    def test_init_idempotent_leaves_state_unchanged(self):
        run_before = self.ws.run_file().read_bytes()
        checkpoint_before = self.ws.checkpoint_file().read_bytes()
        tracker_before = (self.ws.root / "tracker.yaml").read_bytes()
        result = self.ws.run_state(
            "init",
            "--tracker",
            "tracker.yaml",
            "--principles",
            "principles.md",
            "--program",
            "demo",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(run_before, self.ws.run_file().read_bytes())
        self.assertEqual(checkpoint_before, self.ws.checkpoint_file().read_bytes())
        self.assertEqual(tracker_before, (self.ws.root / "tracker.yaml").read_bytes())

    def test_second_program_refused_with_reconcile_instruction(self):
        result = self.ws.run_state(
            "init",
            "--tracker",
            "tracker.yaml",
            "--principles",
            "principles.md",
            "--program",
            "other",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("reconcile", result.stderr)
        self.assertIn("another program is active", result.stderr)
        pointer = json.loads(self.ws.pointer_file().read_text())
        self.assertEqual(".software-factory/runs/demo/run.json", pointer["run"])

    def test_init_requires_source_files_and_slug(self):
        result = self.ws.run_state(
            "init",
            "--tracker",
            "missing.yaml",
            "--principles",
            "principles.md",
            "--program",
            "fresh",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("tracker file missing", result.stderr)
        result = self.ws.run_state(
            "init",
            "--tracker",
            "tracker.yaml",
            "--principles",
            "principles.md",
            "--program",
            "Bad Slug",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("slug", result.stderr)


class ClaimScopeTests(StateFixture):
    def test_invalid_scopes_refused_without_state_change(self):
        repo = self.repo()
        before = self.ws.run_file().read_bytes()
        cases = [
            ("/tmp/absolute.py", "absolute"),
            ("*.py", "glob star"),
            ("src?.py", "glob question"),
            ("src[0].py", "glob bracket"),
            ("../outside", "parent escape"),
            ("", "empty scope"),
            (".", "dot scope"),
            ("src/..", "normalized to root"),
        ]
        for raw, label in cases:
            with self.subTest(case=label):
                result = self.ws.claim("t1", "worker-a", repo, raw)
                self.assertNotEqual(0, result.returncode, label)
                self.assertEqual(before, self.ws.run_file().read_bytes())

    def test_repo_must_be_worktree_root(self):
        repo = self.repo()
        inside = repo / "src"
        inside.mkdir()
        before = self.ws.run_file().read_bytes()
        result = self.ws.claim("t1", "worker-a", inside, "src")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("worktree root", result.stderr)
        self.assertEqual(before, self.ws.run_file().read_bytes())

    def test_valid_claim_records_scope_owner_identity_timestamp(self):
        repo = self.repo()
        result = self.ws.claim("t1", "worker-a", repo, "src/app", "src/lib")
        self.assertEqual(0, result.returncode, result.stderr)
        claim = self.ws.state()["claims"]["t1"]
        self.assertEqual("worker-a", claim["owner"])
        self.assertEqual(["src/app", "src/lib"], claim["paths"])
        self.assertTrue(claim["claimed_at"])
        common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(str((repo / common).resolve()), claim["identity"])
        self.assertEqual(str(repo), claim["repo"])

    def test_release_requires_matching_owner(self):
        repo = self.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        result = self.ws.run_state("release", "--task", "t1", "--owner", "worker-b")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("t1", self.ws.state()["claims"])
        result = self.ws.run_state("release", "--task", "t1", "--owner", "worker-a")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("t1", self.ws.state()["claims"])

    def test_claim_secret_refusal_is_clean(self):
        repo = self.repo()
        before = self.ws.run_file().read_bytes()
        checkpoint_before = self.ws.checkpoint_file().read_bytes()
        # Short synthetic shapes: enough to trip the refusal regex, never real.
        secrets = [
            "sk-ant-fix01",
            "ghp_fix01",
            "-----BEGIN FIXTURE PRIVATE KEY-----",
            "password: fixture",
            "api_key=fixture",
        ]
        for secret in secrets:
            for flag in ("task", "owner"):
                with self.subTest(secret=secret[:12], flag=flag):
                    values = {"task": "t1", "owner": "worker-a"}
                    values[flag] = secret
                    result = self.ws.run_state(
                        "claim", "--repo", repo, "--paths", "src",
                        "--task", values["task"], "--owner", values["owner"],
                    )
                    self.assertNotEqual(0, result.returncode)
                    output = result.stdout + result.stderr
                    self.assertNotIn(secret, output)
                    self.assertIn("credential-like", output)
        self.assertEqual(before, self.ws.run_file().read_bytes())
        self.assertEqual(checkpoint_before, self.ws.checkpoint_file().read_bytes())


class WorktreeCollisionTests(StateFixture):
    def test_collisions_across_worktrees_of_one_common_dir(self):
        origin = self.repo("origin")
        other = self.ws.worktree(origin, "wt2")
        self.assertEqual(0, self.ws.claim("a", "worker-a", origin, "src/a.py").returncode)
        same = self.ws.claim("b", "worker-b", other, "src/a.py")
        self.assertNotEqual(0, same.returncode)
        self.assertIn("collide", same.stderr)
        parent = self.ws.claim("b", "worker-b", other, "src")
        self.assertNotEqual(0, parent.returncode)
        self.assertIn("collide", parent.stderr)
        self.assertEqual(0, self.ws.run_state("release", "--task", "a", "--owner", "worker-a").returncode)
        self.assertEqual(0, self.ws.claim("b", "worker-b", other, "src").returncode)
        child = self.ws.claim("c", "worker-c", origin, "src/b.py")
        self.assertNotEqual(0, child.returncode)
        self.assertIn("collide", child.stderr)
        self.assertEqual(0, self.ws.claim("d", "worker-d", other, "docs/readme.md").returncode)
        unrelated = self.repo("unrelated")
        result = self.ws.claim("e", "worker-e", unrelated, "src/a.py")
        self.assertEqual(0, result.returncode, result.stderr)


class ConcurrencyTests(StateFixture):
    def spawn(self, *args):
        return subprocess.Popen(
            [
                sys.executable,
                str(SCRIPTS / "state.py"),
                "--workspace",
                str(self.ws.root),
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @staticmethod
    def finish(process):
        process.communicate()
        return process.returncode

    def test_same_path_concurrent_claims_yield_one_winner(self):
        repo = self.repo()
        first = self.spawn("claim", "--task", "t1", "--owner", "w1", "--repo", str(repo), "--paths", "src")
        second = self.spawn("claim", "--task", "t2", "--owner", "w2", "--repo", str(repo), "--paths", "src")
        codes = sorted(self.finish(process) for process in (first, second))
        self.assertEqual([0, 2], codes)
        claims = self.ws.state()["claims"]
        self.assertEqual(1, len(claims))
        self.assertEqual(1, len(claims[next(iter(claims))]["paths"]))
        leftovers = [item.name for item in self.ws.runs_dir().iterdir() if item.name.startswith(".factory-")]
        self.assertEqual([], leftovers)

    def test_disjoint_concurrent_claims_both_win(self):
        repo = self.repo()
        first = self.spawn("claim", "--task", "t1", "--owner", "w1", "--repo", str(repo), "--paths", "src/a")
        second = self.spawn("claim", "--task", "t2", "--owner", "w2", "--repo", str(repo), "--paths", "src/b")
        codes = sorted(self.finish(process) for process in (first, second))
        self.assertEqual([0, 0], codes)
        claims = self.ws.state()["claims"]
        self.assertEqual({"t1": ["src/a"], "t2": ["src/b"]}, {k: v["paths"] for k, v in claims.items()})

    def test_interleaved_mutations_keep_state_atomic(self):
        repo = self.repo()
        processes = []
        for index in range(4):
            processes.append(self.spawn("claim", "--task", f"t{index}", "--owner", "w", "--repo", str(repo), "--paths", f"src/f{index}"))
            processes.append(self.spawn("snapshot"))
        for index in range(3):
            processes.append(self.spawn("checkpoint", "--notes", str(self.ws.notes_file(support.notes(), name=f"n{index}.json"))))
        for process in processes:
            self.assertIn(0, (self.finish(process), 2))
        data = self.ws.state()
        self.assertEqual(4, len(data["claims"]))
        self.assertEqual(set(support.notes()), set(data["checkpoint"]))
        leftovers = [item.name for item in self.ws.runs_dir().iterdir() if item.name.startswith(".")]
        self.assertEqual([], leftovers)
        self.assertTrue(self.ws.checkpoint_file().is_file())

    def test_busy_lock_reports_and_waiter_completes(self):
        lock_directory = self.ws.root / ".software-factory"
        holder = (lock_directory / "state.lock").open("a")
        fcntl.flock(holder, fcntl.LOCK_EX)
        original_wait = state.LOCK_WAIT_SECONDS
        state.LOCK_WAIT_SECONDS = 0.2
        try:
            with (
                self.assertRaises(state.StateError) as raised,
                state.locked(self.ws.root),
            ):
                pass
            self.assertIn("state busy", str(raised.exception))
        finally:
            state.LOCK_WAIT_SECONDS = original_wait

        def release_soon():
            time.sleep(0.6)
            fcntl.flock(holder, fcntl.LOCK_UN)

        threading.Thread(target=release_soon).start()
        repo = self.repo()
        result = self.ws.claim("t1", "worker-a", repo, "src")
        self.assertEqual(0, result.returncode, result.stderr)
        holder.close()


class CheckpointTests(StateFixture):
    def test_checkpoint_shape_limits_enforced(self):
        before = self.ws.run_file().read_bytes()
        valid = support.notes()
        invalid = []
        broken = dict(valid, objective="")
        invalid.append(("objective empty", broken))
        invalid.append(("next too long", dict(valid, next="x" * 501)))
        invalid.append(("missing key", {k: v for k, v in valid.items() if k != "open_questions"}))
        invalid.append(("extra key", dict(valid, transcript="extra")))
        invalid.append(("nine items", dict(valid, completed=["x"] * 9)))
        invalid.append(("item too long", dict(valid, decisions=["x" * 501])))
        invalid.append(("list is string", dict(valid, completed="evidence.txt")))
        for label, note_set in invalid:
            with self.subTest(case=label):
                result = self.ws.checkpoint(note_set)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, self.ws.run_file().read_bytes())

    def test_valid_checkpoint_persists_and_regenerates_projection(self):
        note_set = support.notes()
        result = self.ws.checkpoint(note_set)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(note_set, self.ws.state()["checkpoint"])
        rendered = self.ws.checkpoint_file().read_text()
        self.assertIn("Ship story 1", rendered)
        self.assertIn("## Completed", rendered)
        self.assertIn("demo", rendered)

    def test_checkpoint_secret_refusal_is_clean(self):
        before = self.ws.run_file().read_bytes()
        for secret in ("password: fixture", "sk-ant-fix02", "api_key=fixture2"):
            with self.subTest(secret=secret[:10]):
                result = self.ws.checkpoint(dict(support.notes(), next="then " + secret))
                self.assertNotEqual(0, result.returncode)
                output = result.stdout + result.stderr
                self.assertNotIn(secret, output)
                self.assertIn("credential-like", output)
        self.assertEqual(before, self.ws.run_file().read_bytes())
        self.assertNotIn("password: fixture", self.ws.checkpoint_file().read_text())


class SnapshotTests(StateFixture):
    def test_git_failure_degrades_to_unknown_and_recovers(self):
        repo = self.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        self.assertEqual(0, self.ws.checkpoint(support.notes()).returncode)
        git_dir = repo / ".git"
        shutil.move(str(git_dir), str(self.ws.root / "git-backup"))
        result = self.ws.snapshot()
        self.assertEqual(0, result.returncode, result.stderr)
        observation = self.ws.state()["claims"]["t1"]["observation"]
        self.assertEqual("unknown", observation["head"])
        self.assertEqual("unknown", observation["dirty"])
        self.assertEqual(support.notes(), self.ws.state()["checkpoint"])
        self.assertNotIn("Traceback", result.stderr)
        shutil.move(str(self.ws.root / "git-backup"), str(git_dir))
        result = self.ws.snapshot()
        self.assertEqual(0, result.returncode, result.stderr)
        observation = self.ws.state()["claims"]["t1"]["observation"]
        self.assertRegex(observation["head"], r"^[0-9a-f]{40}$")
        self.assertIs(False, observation["dirty"])

    def test_snapshot_leaves_unchanged_claims_untouched(self):
        first = self.repo("r1")
        second = self.repo("r2")
        self.assertEqual(0, self.ws.claim("t1", "worker-a", first, "src").returncode)
        self.assertEqual(0, self.ws.claim("t2", "worker-b", second, "src").returncode)
        self.assertEqual(0, self.ws.checkpoint(support.notes()).returncode)
        self.assertEqual(0, self.ws.snapshot().returncode)
        before = self.ws.state()["claims"]
        shutil.move(str(second / ".git"), str(self.ws.root / "r2-git"))
        self.assertEqual(0, self.ws.snapshot().returncode)
        after = self.ws.state()["claims"]
        self.assertEqual("unknown", after["t2"]["observation"]["head"])
        self.assertEqual(before["t1"]["observation"], after["t1"]["observation"])
        self.assertEqual(support.notes(), self.ws.state()["checkpoint"])


class StatusTests(StateFixture):
    def test_status_is_read_only(self):
        self.assertEqual(0, self.ws.claim("t1", "worker-a", self.repo(), "src").returncode)
        self.assertEqual(0, self.ws.checkpoint(support.notes()).returncode)
        before = {path: digest(path) for path in (self.ws.run_file(), self.ws.checkpoint_file(), self.ws.pointer_file())}
        result = self.ws.run_state("status")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Ship story 1", result.stdout)
        after = {path: digest(path) for path in (self.ws.run_file(), self.ws.checkpoint_file(), self.ws.pointer_file())}
        self.assertEqual(before, after)

    def test_status_without_pointer_fails_safely(self):
        self.ws.pointer_file().unlink()
        result = self.ws.run_state("status")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(1, len(result.stderr.strip().splitlines()))
        self.assertIn("reconcile", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("{", result.stderr)


class DeactivateRepairTests(StateFixture):
    def test_deactivate_requires_released_claims_then_archives(self):
        repo = self.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        refused = self.ws.run_state("deactivate", "--program", "demo")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("release", refused.stderr)
        self.assertTrue(self.ws.pointer_file().is_file())
        self.assertEqual(0, self.ws.run_state("release", "--task", "t1", "--owner", "worker-a").returncode)
        result = self.ws.run_state("deactivate", "--program", "demo")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.ws.pointer_file().exists())
        archives = list((self.ws.root / ".software-factory").glob("inactive-*.json"))
        self.assertEqual(1, len(archives))
        self.assertTrue(self.ws.run_file().is_file())

    def test_deactivate_refuses_program_mismatch(self):
        result = self.ws.run_state("deactivate", "--program", "other")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("mismatch", result.stderr)
        self.assertTrue(self.ws.pointer_file().is_file())

    def test_repair_refuses_other_active_program(self):
        self.assertEqual(0, self.ws.run_state("deactivate", "--program", "demo").returncode)
        result = self.ws.run_state(
            "init", "--tracker", "tracker.yaml", "--principles", "principles.md", "--program", "other"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        pointer_before = self.ws.pointer_file().read_bytes()
        result = self.ws.run_state("repair", "--program", "demo")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("deactivate", result.stderr)
        self.assertEqual(pointer_before, self.ws.pointer_file().read_bytes())

    def test_repair_archives_corrupt_pointer_and_restores(self):
        self.ws.pointer_file().write_text("broken")
        result = self.ws.run_state("repair", "--program", "demo")
        self.assertEqual(0, result.returncode, result.stderr)
        archives = list((self.ws.root / ".software-factory").glob("before-repair-*.json"))
        self.assertEqual(1, len(archives))
        self.assertEqual("broken", archives[0].read_text())
        pointer = json.loads(self.ws.pointer_file().read_text())
        self.assertEqual(".software-factory/runs/demo/run.json", pointer["run"])
        self.assertEqual("demo", self.ws.state()["program"])

    def test_repair_unknown_slug_creates_nothing(self):
        result = self.ws.run_state("repair", "--program", "ghost")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.ws.root / ".software-factory" / "runs" / "ghost").exists())


class CorruptStateTests(StateFixture):
    def test_invalid_run_refused(self):
        data = self.ws.state()
        del data["tracker"]
        self.ws.run_file().write_text(json.dumps(data))
        with self.assertRaises(state.StateError):
            state.load(self.ws.root)
        with self.assertRaises(state.StateError):
            state.repair(self.ws.root, "demo")

    def test_invalid_observation_refused(self):
        repo = self.repo()
        self.assertEqual(0, self.ws.claim("t1", "worker-a", repo, "src").returncode)
        data = self.ws.state()
        data["claims"]["t1"]["observation"] = "corrupt"
        self.ws.run_file().write_text(json.dumps(data))
        with self.assertRaises(state.StateError):
            state.load(self.ws.root)

    def test_escaping_pointer_refused(self):
        self.ws.pointer_file().write_text('{"version": 1, "run": "../../outside.json"}')
        with self.assertRaises(state.StateError):
            state.load(self.ws.root)

    def test_source_drift_rejected(self):
        (self.ws.root / "other.yaml").write_text("different\n")
        result = self.ws.run_state(
            "init", "--tracker", "other.yaml", "--principles", "principles.md", "--program", "demo"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("source links differ", result.stderr)


class HelperSafetyTests(unittest.TestCase):
    def setUp(self):
        self.ws = support.Workspace()
        self.addCleanup(self.ws.cleanup)

    def test_imports_are_standard_library_only(self):
        self.assertEqual([], support.non_stdlib_imports(SCRIPTS / "state.py"))

    def test_no_network_or_model_client_modules(self):
        modules = support.imported_top_modules(SCRIPTS / "state.py")
        for banned in ("socket", "urllib", "http", "ssl", "requests", "anthropic", "openai"):
            self.assertNotIn(banned, modules)

    def test_git_usage_is_read_only(self):
        source = (SCRIPTS / "state.py").read_text()
        for line in source.splitlines():
            if '"git"' in line:
                for writer in ("commit", "push", "merge", "checkout", "reset", "clean", "stash", "fetch"):
                    self.assertNotIn(writer, line, line)

    def test_lifecycle_never_invokes_host_clis(self):
        env, log, stub_dir = support.guard_env()
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        repo = self.ws.repo()
        commands = [
            self.ws.claim("t1", "worker-a", repo, "src", env=env),
            self.ws.snapshot(env=env),
            self.ws.checkpoint(support.notes(), env=env),
            self.ws.run_state("status", env=env),
            self.ws.run_state("release", "--task", "t1", "--owner", "worker-a", env=env),
        ]
        for result in commands:
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(log.exists() and log.read_text())

    def test_atomic_write_helpers_exist(self):
        source = (SCRIPTS / "state.py").read_text()
        for anchor in ("mkstemp", "os.replace", "fsync", "fcntl", "state busy"):
            self.assertIn(anchor, source)


if __name__ == "__main__":
    unittest.main()
