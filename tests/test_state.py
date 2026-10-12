"""Tests for the execution-state kernel helper (state.py).

Encodes the VAL-KERNEL state assertions: neutral run paths, idempotent init,
the missing/empty principles-file guard with the path named and no fallback,
claim scope validation, worktree identity collisions, concurrency, checkpoint
shape limits, credential refusal, degraded Git observation, read-only status,
deactivate/repair ownership, atomic lock-protected writes, and the kernel
bounds — claim cap with a reconcile path, per-worktree (not per-claim)
snapshot Git cost, no Git subprocess under the state lock, a bounded
run.json with bounded release history, and the audited run-folder layout
with its size budget and binary refusal.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
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


class PrinciplesPathGuardTests(StateFixture):
    """VAL-KERNEL-020: a missing or empty principles file is a blocked state.

    Missing, zero-byte and whitespace-only principles files are each refused
    with a nonzero result naming the offending path; there is no silent
    fallback to a built-in default.
    """

    def run_init(self, principles, program="fresh"):
        return self.ws.run_state(
            "init",
            "--tracker",
            "tracker.yaml",
            "--principles",
            principles,
            "--program",
            program,
        )

    def test_missing_principles_file_refused_with_path_named(self):
        result = self.run_init("missing-principles.md")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("principles file missing", result.stderr)
        self.assertIn("missing-principles.md", result.stderr)
        self.assertFalse((self.ws.root / ".software-factory" / "runs" / "fresh").exists())

    def test_zero_byte_principles_file_refused_with_path_named(self):
        path = self.ws.root / "principles.md"
        path.write_bytes(b"")
        run_before = self.ws.run_file().read_bytes()
        result = self.run_init("principles.md", program="demo")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("principles file empty", result.stderr)
        self.assertIn("principles.md", result.stderr)
        # No silent fallback: the empty file and the recorded run stay untouched.
        self.assertEqual(b"", path.read_bytes())
        self.assertEqual(run_before, self.ws.run_file().read_bytes())

    def test_whitespace_only_principles_file_refused(self):
        path = self.ws.root / "principles.md"
        path.write_text(" \n\t\n   \n")
        result = self.run_init("principles.md", program="demo")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("principles file empty", result.stderr)
        self.assertIn("principles.md", result.stderr)
        self.assertEqual(" \n\t\n   \n", path.read_text())

    def test_initialize_raises_state_error_for_empty_principles(self):
        (self.ws.root / "empty.md").write_text("\n\n")
        with self.assertRaises(state.StateError) as caught:
            state.initialize(self.ws.root, "fresh", "tracker.yaml", "empty.md")
        self.assertIn("empty.md", str(caught.exception))

    def test_repair_refuses_empty_principles_consistently(self):
        (self.ws.root / "principles.md").write_bytes(b"")
        result = self.ws.run_state("repair", "--program", "demo")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("principles file empty", result.stderr)
        self.assertIn("principles.md", result.stderr)


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


class SnapshotBoundTests(StateFixture):
    """VAL-KERNEL-017: snapshot Git cost is per worktree, never per claim."""

    def git_recorder(self):
        """A `git` stub first on PATH that logs argv and execs the real git."""
        real = shutil.which("git")
        stub_dir = Path(tempfile.mkdtemp(prefix="sf-git-rec-"))
        self.addCleanup(shutil.rmtree, stub_dir, ignore_errors=True)
        log = stub_dir / "git.log"
        stub = stub_dir / "git"
        stub.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$SF_GIT_LOG\"\n"
            f'exec "{real}" "$@"\n'
        )
        stub.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(stub_dir) + os.pathsep + env.get("PATH", "")
        env["SF_GIT_LOG"] = str(log)
        return env, log

    def fill_shared_worktrees(self, count):
        """Add `count` disjoint claims across two worktrees of one repo."""
        repo = self.repo()
        other = self.ws.worktree(repo, "wt2")
        resolved, identity, _ = state.prepare_claim(repo, ["x"])
        resolved_other, identity_other, _ = state.prepare_claim(other, ["x"])
        self.assertEqual(identity, identity_other)
        path, data = state.load(self.ws.root)
        for index in range(count):
            target = resolved if index % 2 == 0 else resolved_other
            state.claim(
                data, f"t{index:03d}", f"worker-{index % 4}", target, identity,
                [f"src/f{index:03d}"],
            )
        state.save(path, data)

    def test_snapshot_git_cost_depends_on_worktrees_not_claims(self):
        self.fill_shared_worktrees(50)
        env, log = self.git_recorder()
        result = self.ws.snapshot(env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        calls = log.read_text().splitlines()
        # Two read-only calls per distinct worktree, independent of claim count.
        self.assertEqual(4, len(calls))
        self.assertEqual(2, sum("rev-parse" in line for line in calls))
        self.assertEqual(2, sum("status" in line for line in calls))
        claims = self.ws.state()["claims"]
        self.assertEqual(50, len(claims))
        for item in claims.values():
            self.assertRegex(item["observation"]["head"], r"^[0-9a-f]{40}$")
            self.assertIs(False, item["observation"]["dirty"])
        # A second snapshot stays bounded and keeps unchanged observations verbatim.
        before = self.ws.state()["claims"]
        result = self.ws.snapshot(env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(8, len(log.read_text().splitlines()))
        self.assertEqual(before, self.ws.state()["claims"])

    def test_no_git_subprocess_while_state_locked(self):
        repo = self.repo()
        lock_file = self.ws.root / ".software-factory" / "state.lock"
        real_git = state.git
        calls = []

        def recording_git(repo_arg, *args):
            # flock is per open file description: this probe fails exactly when
            # the helper itself holds the state lock on its own descriptor.
            probe = lock_file.open("a")
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                calls.append(("locked", args))
            else:
                fcntl.flock(probe, fcntl.LOCK_UN)
                calls.append(("free", args))
            finally:
                probe.close()
            return real_git(repo_arg, *args)

        state.git = recording_git
        original_argv = sys.argv
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sys.argv = [
                    "state.py", "--workspace", str(self.ws.root),
                    "claim", "--task", "t1", "--owner", "w1",
                    "--repo", str(repo), "--paths", "src",
                ]
                self.assertEqual(0, state.main())
                sys.argv = ["state.py", "--workspace", str(self.ws.root), "snapshot"]
                self.assertEqual(0, state.main())
        finally:
            state.git = real_git
            sys.argv = original_argv
        self.assertTrue(calls)
        self.assertEqual([], [entry for entry in calls if entry[0] == "locked"])


class ClaimBoundTests(StateFixture):
    """VAL-KERNEL-017: claim accumulation is bounded with a reconcile path."""

    def fill(self, count):
        repo = self.repo()
        resolved, identity, _ = state.prepare_claim(repo, ["x"])
        path, data = state.load(self.ws.root)
        for index in range(count):
            state.claim(
                data, f"t{index:03d}", "worker-a", resolved, identity,
                [f"src/f{index:03d}"],
            )
        state.save(path, data)
        return resolved

    def test_claim_cap_refuses_with_reconcile_path(self):
        repo = self.fill(state.MAX_ACTIVE_CLAIMS)
        before = self.ws.run_file().read_bytes()
        result = self.ws.claim("overflow", "worker-b", repo, "src/overflow")
        self.assertEqual(2, result.returncode)
        self.assertIn("claim cap", result.stderr)
        self.assertIn("release", result.stderr)
        self.assertIn("reconcile", result.stderr)
        self.assertEqual(before, self.ws.run_file().read_bytes())

    def test_claims_above_threshold_warn_but_succeed(self):
        repo = self.fill(state.CLAIM_WARN_THRESHOLD)
        result = self.ws.claim("one-more", "worker-b", repo, "src/one-more")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(str(state.CLAIM_WARN_THRESHOLD + 1), result.stderr)
        self.assertIn("release", result.stderr)

    def test_reconcile_lists_stale_claims_and_never_expires(self):
        repo = self.repo()
        other = self.repo("other")
        self.assertEqual(0, self.ws.claim("gone", "worker-a", repo, "src").returncode)
        self.assertEqual(0, self.ws.claim("alive", "worker-b", other, "src").returncode)
        shutil.rmtree(repo)
        result = self.ws.run_state("reconcile")
        self.assertEqual(1, result.returncode)
        self.assertIn("gone", result.stdout)
        self.assertIn("worker-a", result.stdout)
        self.assertNotIn("alive", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        # The stale claim survives until an owner-checked release, and
        # deactivate still refuses while any claim is live.
        self.assertIn("gone", self.ws.state()["claims"])
        refused = self.ws.run_state("deactivate", "--program", "demo")
        self.assertNotEqual(0, refused.returncode)
        self.assertTrue(self.ws.pointer_file().is_file())

    def test_reconcile_clean_when_everything_resolves(self):
        self.assertEqual(0, self.ws.claim("t1", "worker-a", self.repo(), "src").returncode)
        result = self.ws.run_state("reconcile")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("no stale claims", result.stdout)

    def test_reconcile_output_is_sanitized(self):
        data = self.ws.state()
        data["claims"]["evil"] = {
            "owner": "w\x007",
            "repo": str(self.ws.root / "ghost"),
            "identity": "i",
            "paths": ["src"],
            "claimed_at": "2026-01-01T00:00:00+00:00",
        }
        self.ws.run_file().write_text(json.dumps(data))
        result = self.ws.run_state("reconcile")
        self.assertEqual(1, result.returncode)
        self.assertNotIn("\x00", result.stdout)
        self.assertIn("evil", result.stdout)

    def test_release_prunes_claim_and_keeps_bounded_history(self):
        repo = self.repo()
        total = state.HISTORY_LIMIT + 2
        for index in range(total):
            self.assertEqual(
                0, self.ws.claim(f"t{index}", "w", repo, f"src/f{index}").returncode
            )
        for index in range(total):
            self.assertEqual(
                0,
                self.ws.run_state("release", "--task", f"t{index}", "--owner", "w").returncode,
            )
        data = self.ws.state()
        self.assertEqual({}, data["claims"])
        history = data["history"]
        self.assertEqual(state.HISTORY_LIMIT, len(history))
        self.assertEqual(f"t{total - 1}", history[-1]["task"])
        self.assertEqual("t2", history[0]["task"])
        self.assertEqual({"task", "owner", "released_at"}, set(history[-1]))


class RunBudgetTests(StateFixture):
    """VAL-KERNEL-018: run.json stays bounded; oversized state refused whole."""

    def test_run_json_stays_under_budget_at_the_claim_cap(self):
        repo = self.repo()
        resolved, identity, _ = state.prepare_claim(repo, ["x"])
        path, data = state.load(self.ws.root)
        for index in range(state.MAX_ACTIVE_CLAIMS):
            state.claim(
                data, f"task-{index:03d}", f"worker-{index % 8}", resolved, identity,
                [f"src/area/file-{index:03d}.py"],
            )
        data["checkpoint"] = support.notes()
        state.save(path, data)
        size = self.ws.run_file().stat().st_size
        self.assertLess(size, state.MAX_RUN_BYTES)
        parsed = json.loads(self.ws.run_file().read_text())
        state.validate_state(parsed)

    def test_oversized_run_state_refused_whole(self):
        data = self.ws.state()
        data["pad"] = "x" * state.MAX_RUN_BYTES
        self.ws.run_file().write_text(json.dumps(data))
        for command in ("status", "snapshot"):
            with self.subTest(command=command):
                result = self.ws.run_state(command)
                self.assertEqual(2, result.returncode)
                self.assertIn("budget", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(1, len(result.stderr.strip().splitlines()))
                self.assertNotIn("xxx", result.stderr)


class RunFolderAuditTests(StateFixture):
    """VAL-KERNEL-019: layout contract, size budget, binary refusal, read-only."""

    def file_digests(self):
        return {
            path: digest(path)
            for path in (self.ws.root / ".software-factory").rglob("*")
            if path.is_file()
        }

    def test_audit_reports_usage_and_accepts_documented_layout(self):
        runs = self.ws.runs_dir()
        for folder in ("notes", "briefs", "evidence", "evals", "handoffs"):
            target = runs / folder
            target.mkdir()
            (target / "receipt.md").write_text("receipt: ok\n")
        before = self.file_digests()
        result = self.ws.run_state("audit")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("budget", result.stdout)
        self.assertIn("bytes", result.stdout)
        self.assertEqual(before, self.file_digests())

    def test_audit_flags_binary_artifact(self):
        evidence = self.ws.runs_dir() / "evidence"
        evidence.mkdir()
        (evidence / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x0d")
        before = self.file_digests()
        result = self.ws.run_state("audit")
        self.assertEqual(1, result.returncode)
        self.assertIn("binary", result.stderr)
        self.assertIn("shot.png", result.stderr)
        self.assertEqual(before, self.file_digests())

    def test_audit_flags_oversized_artifact(self):
        evidence = self.ws.runs_dir() / "evidence"
        evidence.mkdir()
        (evidence / "trace.json").write_text("x" * (state.MAX_ARTIFACT_BYTES + 1))
        result = self.ws.run_state("audit")
        self.assertEqual(1, result.returncode)
        self.assertIn("trace.json", result.stderr)
        self.assertIn("limit", result.stderr)

    def test_audit_flags_undocumented_entries(self):
        runs = self.ws.runs_dir()
        (runs / "BOARD.md").write_text("derived board\n")
        (runs.parent / "stray.txt").write_text("stray\n")
        result = self.ws.run_state("audit")
        self.assertEqual(1, result.returncode)
        self.assertIn("BOARD.md", result.stderr)
        self.assertIn("stray.txt", result.stderr)
        self.assertIn("undocumented", result.stderr)

    def test_audit_flags_symlinks(self):
        evidence = self.ws.runs_dir() / "evidence"
        evidence.mkdir()
        (evidence / "real.md").write_text("real\n")
        os.symlink(evidence / "real.md", evidence / "link.md")
        result = self.ws.run_state("audit")
        self.assertEqual(1, result.returncode)
        self.assertIn("link.md", result.stderr)

    def test_audit_flags_over_budget_without_mutating(self):
        evidence = self.ws.runs_dir() / "evidence"
        evidence.mkdir()
        (evidence / "big.md").write_text("x" * 4096)
        before = self.file_digests()
        _, _, problems = state.audit_runs(self.ws.root, budget=1024)
        self.assertTrue(any("budget" in problem for problem in problems))
        _, _, problems = state.audit_runs(self.ws.root)
        self.assertEqual([], problems)
        self.assertEqual(before, self.file_digests())


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
