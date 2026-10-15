"""Run auditing covers producer receipts, invalid layouts and unreadable entries."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

state = support.helper("state")


class RunAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runs = self.root / ".software-factory" / "runs"
        self.runs.mkdir(parents=True)

    def artifact(self, relative, content=b"receipt\n"):
        path = self.runs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def audit_cli(self):
        return support.run("state", "audit", "--workspace", self.root)

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()
        }

    def test_real_eval_state_run_audits_clean_without_changing_bytes(self):
        (self.root / "ready.txt").write_text("ready\n")
        plan = self.root / "eval.json"
        plan.write_text(json.dumps({
            "version": 1,
            "surfaces": [{"id": "local"}],
            "cases": [{
                "id": "LOCAL-AUDIT-001", "story": "audit", "surface": "local",
                "criterion": "The state fixture exists", "kind": "pass_to_pass",
                "grade": {"type": "state", "path": "ready.txt", "contains": ["ready"]},
            }],
        }))
        result = subprocess.run(
            [sys.executable, str(support.REPO / "skills/sf-eval/scripts/sf_eval.py"),
             "run", "--plan", str(plan), "--mode", "premerge",
             "--project-root", str(self.root)],
            capture_output=True, text=True, check=False, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        receipts = list(self.runs.glob("*/evals/receipt.json"))
        self.assertEqual(1, len(receipts))
        self.assertEqual("pass", json.loads(receipts[0].read_text())["verdict"])
        before = self.snapshot()
        audit = self.audit_cli()
        self.assertEqual(0, audit.returncode, audit.stderr)
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual([], problems)
        self.assertEqual(2, files)
        self.assertEqual(sum(path.stat().st_size for path in self.runs.rglob("*.json")), total)
        self.assertEqual(before, self.snapshot())

    def test_historical_eval_modes_and_collision_suffixes_are_preserved(self):
        for mode in ("quick", "epic", "premerge", "canary"):
            for suffix in ("", "-2", "-123456789"):
                self.artifact(f"r-20240229T235959Z-{mode}{suffix}/evals/receipt.json", b"{}\n")
        before = self.snapshot()
        self.assertEqual((36, 12, []), state.audit_runs(self.root))
        self.assertEqual(before, self.snapshot())

    def test_eval_recognition_has_timestamp_mode_and_suffix_bounds(self):
        invalid = (
            "r-20260229T000000Z-premerge", "r-20261301T000000Z-premerge",
            "r-20261015T240000Z-premerge", "r-20261015T120060Z-premerge",
            "r-20261015T000000Z-other", "r-20261015T000000Z-quick-0",
            "r-20261015T000000Z-quick-02", "r-20261015T000000Z-quick-",
            "r-20261015T000000Z-premerge-extra", "r-20261015t000000z-premerge",
        )
        for name in invalid:
            with self.subTest(name=name):
                self.assertFalse(state.is_eval_run_id(name))
        for name in invalid[:-1]:
            self.artifact(f"{name}/evals/receipt.json", b"{}")
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual(18, total)
        self.assertEqual(9, files)
        self.assertEqual(9, len(problems))
        self.assertTrue(all("undocumented" in problem for problem in problems))

    def test_program_slug_rules_are_unchanged(self):
        base = {"version": 1, "claims": {}, "checkpoint": {},
                "tracker": "tracker.json", "principles": "principles.md"}
        for name in ("a", "a" * 64, "r-20261015t000000z-premerge"):
            with self.subTest(name=name):
                state.validate_state({**base, "program": name})
        for name in ("a" * 65, "Bad", "r-20261015T000000Z-premerge"):
            with self.subTest(name=name):
                with self.assertRaises(state.StateError):
                    state.validate_state({**base, "program": name})
                with self.assertRaisesRegex(state.StateError, "lowercase slug"):
                    state.initialize(self.root, name, "unused", "unused")

    def test_invalid_directory_names_cannot_hide_budget_binary_or_artifact_limits(self):
        self.artifact("Bad Name/unknown/deep/blob.bin", b"\0" + b"x" * 32)
        before = self.snapshot()
        total, files, problems = state.audit_runs(self.root, budget=16, artifact_limit=16)
        self.assertEqual((33, 1), (total, files))
        for expected in ("undocumented", "binary", "artifact above", "above the 16-byte budget"):
            self.assertTrue(any(expected in item for item in problems), problems)
        self.assertEqual(before, self.snapshot())

    def test_stray_top_level_files_are_measured_and_inspected(self):
        self.artifact("loose.bin", b"\0" + b"x" * 16)
        self.artifact("stray.txt", b"text")
        total, files, problems = state.audit_runs(self.root, budget=20, artifact_limit=16)
        self.assertEqual((21, 2), (total, files))
        self.assertEqual(2, sum("undocumented" in item for item in problems))
        for expected in ("binary", "artifact above", "above the 20-byte budget"):
            self.assertTrue(any(expected in item for item in problems), problems)

    def test_run_document_cap_applies_under_invalid_names_too(self):
        self.artifact("Bad/run.json", b" " * (state.MAX_RUN_BYTES + 1))
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual((state.MAX_RUN_BYTES + 1, 1), (total, files))
        self.assertTrue(any("run.json above" in item for item in problems))

    def test_symlinks_at_each_depth_never_count_or_touch_the_target(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "secret.bin"
        target.write_bytes(b"\0" * 128)
        (self.runs / "linked-program").symlink_to(outside, target_is_directory=True)
        evidence = self.runs / "demo" / "evidence"
        evidence.mkdir(parents=True)
        (evidence.parent / "notes").symlink_to(outside, target_is_directory=True)
        (evidence / "linked-file").symlink_to(target)
        (evidence / "linked-dir").symlink_to(outside, target_is_directory=True)
        (evidence / "broken").symlink_to(outside / "absent")
        before = target.read_bytes()
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual((0, 0), (total, files))
        self.assertEqual(5, len(problems))
        self.assertTrue(all("symlink refused" in item for item in problems))
        self.assertEqual(before, target.read_bytes())

    def test_runs_root_symlink_is_refused_without_following_it(self):
        self.runs.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "receipt").write_bytes(b"private fixture\0")
        self.runs.symlink_to(outside, target_is_directory=True)
        before = self.snapshot()
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual((0, 0), (total, files))
        self.assertTrue(any("symlink refused" in item for item in problems))
        self.assertEqual(1, self.audit_cli().returncode)
        self.assertEqual(before, self.snapshot())

    def test_runs_root_regular_file_is_measured_and_refused(self):
        self.runs.rmdir()
        self.runs.write_bytes(b"\0payload")
        total, files, problems = state.audit_runs(self.root, budget=4, artifact_limit=4)
        self.assertEqual((8, 1), (total, files))
        for expected in ("undocumented", "binary", "artifact above", "above the 4-byte budget"):
            self.assertTrue(any(expected in item for item in problems), problems)
        self.assertEqual(1, self.audit_cli().returncode)

    def test_missing_runs_root_is_a_valid_empty_audit(self):
        self.runs.rmdir()
        self.assertEqual((0, 0, []), state.audit_runs(self.root))
        self.assertEqual(0, self.audit_cli().returncode)
        self.assertFalse(self.runs.exists())

    def test_symlinked_state_home_is_refused(self):
        self.runs.rmdir()
        home = self.runs.parent
        home.rmdir()
        outside = self.root / "outside"
        (outside / "runs/demo/evals").mkdir(parents=True)
        (outside / "runs/demo/evals/receipt.json").write_text("{}")
        home.symlink_to(outside, target_is_directory=True)
        total, files, problems = state.audit_runs(self.root)
        self.assertEqual((0, 0), (total, files))
        self.assertTrue(any("incomplete measurement" in item for item in problems))

    def assert_incomplete_failure(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, state.audit(self.root))
        self.assertIn("incomplete measurement", stderr.getvalue())
        self.assertNotIn("sensitive diagnostic", stderr.getvalue())

    def test_directory_scan_permission_error_is_explicitly_incomplete(self):
        path = self.artifact("demo/evidence/receipt.txt")
        blocked = path.parent.stat().st_ino
        original = os.scandir

        def scan(descriptor):
            if os.fstat(descriptor).st_ino == blocked:
                raise PermissionError("sensitive diagnostic")
            return original(descriptor)

        with mock.patch.object(state.os, "scandir", side_effect=scan):
            self.assert_incomplete_failure()

    def test_entry_stat_permission_error_is_explicitly_incomplete(self):
        path = self.artifact("demo/evidence/receipt.txt")
        blocked = path.parent.stat().st_ino
        original = os.scandir

        def scan(descriptor):
            if os.fstat(descriptor).st_ino == blocked:
                entry = mock.Mock()
                entry.name = "receipt.txt"
                entry.stat.side_effect = PermissionError("sensitive diagnostic")
                return contextlib.nullcontext(iter([entry]))
            return original(descriptor)

        with mock.patch.object(state.os, "scandir", side_effect=scan):
            self.assert_incomplete_failure()

    def test_partial_directory_scan_still_counts_observed_files(self):
        path = self.artifact("demo/evidence/receipt.txt")
        blocked = path.parent.stat().st_ino
        original = os.scandir

        @contextlib.contextmanager
        def partial(descriptor):
            with original(descriptor) as iterator:
                def entries():
                    yield next(iterator)
                    raise PermissionError("sensitive diagnostic")
                yield entries()

        def scan(descriptor):
            if os.fstat(descriptor).st_ino == blocked:
                return partial(descriptor)
            return original(descriptor)

        with mock.patch.object(state.os, "scandir", side_effect=scan):
            total, files, problems = state.audit_runs(self.root)
            self.assertEqual((8, 1), (total, files))
            self.assertTrue(any("incomplete measurement" in item for item in problems))
            self.assert_incomplete_failure()

    def test_file_open_permission_error_counts_known_bytes_but_fails_incomplete(self):
        self.artifact("demo/evidence/receipt.txt")
        original = os.open

        def open_file(name, *args, **kwargs):
            if name == "receipt.txt":
                raise PermissionError("sensitive diagnostic")
            return original(name, *args, **kwargs)

        with mock.patch.object(state.os, "open", side_effect=open_file):
            total, files, problems = state.audit_runs(self.root)
            self.assertEqual((8, 1), (total, files))
            self.assertTrue(any("incomplete measurement" in item for item in problems))
            self.assert_incomplete_failure()

    def test_file_read_error_is_explicitly_incomplete_without_losing_known_size(self):
        path = self.artifact("demo/evidence/receipt.txt")
        blocked = path.stat().st_ino
        original = os.read

        def read(descriptor, limit):
            if os.fstat(descriptor).st_ino == blocked:
                raise PermissionError("sensitive diagnostic")
            return original(descriptor, limit)

        with mock.patch.object(state.os, "read", side_effect=read):
            total, files, problems = state.audit_runs(self.root)
            self.assertEqual((8, 1), (total, files))
            self.assertTrue(any("incomplete measurement" in item for item in problems))
            self.assert_incomplete_failure()

    def test_directory_replaced_by_symlink_between_stat_and_open_is_not_followed(self):
        path = self.artifact("demo/evidence/receipt.txt")
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "binary.bin"
        target.write_bytes(b"\0" * 128)
        original = os.open
        replaced = False

        def open_entry(name, *args, **kwargs):
            nonlocal replaced
            if name == "evidence" and not replaced:
                replaced = True
                path.parent.rename(self.root / "saved-evidence")
                path.parent.symlink_to(outside, target_is_directory=True)
            return original(name, *args, **kwargs)

        with mock.patch.object(state.os, "open", side_effect=open_entry):
            total, files, problems = state.audit_runs(self.root)
        self.assertTrue(replaced)
        self.assertEqual((0, 0), (total, files))
        self.assertTrue(any("incomplete measurement" in item for item in problems))
        self.assertFalse(any("binary" in item for item in problems))
        self.assertEqual(b"\0" * 128, target.read_bytes())

    def test_root_stat_permission_error_fails_incomplete(self):
        original = os.stat

        def stat_entry(name, *args, **kwargs):
            if name == "runs":
                raise PermissionError("sensitive diagnostic")
            return original(name, *args, **kwargs)

        with mock.patch.object(state.os, "stat", side_effect=stat_entry):
            self.assert_incomplete_failure()


if __name__ == "__main__":
    unittest.main()
