"""Board updates serialize across processes and fail closed on broken ownership."""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
import time
import unittest
from unittest import mock

import support
from test_board import Board

roadmap = support.helper("roadmap")

# Pause a real CLI process after its authoritative read. Its sibling must wait
# for the board lock, then read the committed record rather than an old copy.
CHILD = r"""
import contextlib
import importlib.util
import json
import sys
import time
from pathlib import Path

module_path, arguments, hook, paused, release, attempted = sys.argv[1:]
spec = importlib.util.spec_from_file_location("board_child", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_lock = module.board_locked

@contextlib.contextmanager
def observed_lock(workspace):
    if attempted:
        Path(attempted).write_text("attempting board lock")
    with original_lock(workspace):
        yield

module.board_locked = observed_lock
if hook:
    original_read = getattr(module, hook)
    def paused_read(*args, **kwargs):
        result = original_read(*args, **kwargs)
        Path(paused).write_text("authoritative record read")
        deadline = time.monotonic() + 10
        while not Path(release).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("test synchronization timed out")
            time.sleep(0.01)
        return result
    setattr(module, hook, paused_read)
sys.argv = [module_path, *json.loads(arguments)]
raise SystemExit(module.main())
"""


class BoardConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.board = Board(self)
        self.board.derive()
        self.processes = []
        self.addCleanup(self.stop_processes)

    def stop_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)

    def start(self, arguments, *, hook="", marker="", release="", attempted=""):
        process = subprocess.Popen(
            [sys.executable, "-c", CHILD, str(support.SCRIPTS / "roadmap.py"),
             json.dumps(["--workspace", str(self.board.root), *arguments]),
             hook, str(marker), str(release), str(attempted)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def wait_for(self, marker, process):
        deadline = time.monotonic() + 5
        while not marker.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"child exited before synchronization: {stdout} {stderr}")
            if time.monotonic() >= deadline:
                self.fail("child did not reach the synchronization point")
            time.sleep(0.01)

    def assert_board_lock_held(self):
        path = self.board.root / ".software-factory" / "board.lock"
        with path.open("a") as stream, self.assertRaises(BlockingIOError):
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def finish(self, process, expected=0):
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(expected, process.returncode, f"{stdout}\n{stderr}")
        return stderr

    def worker_args(self, label, *, review=False):
        receipt = self.board.receipt(f"{label}.json")
        arguments = ["update", "--story", "1", "--actor", "worker", "--owner", "worker",
                     "--receipt", f"{label}={receipt}", "--finding", f"{label} finding"]
        if review:
            arguments.extend(["--status", "in-review"])
        return arguments

    def test_separate_process_updates_preserve_both_receipts_and_findings(self):
        self.board.make_ready(1, "worker", "src/state.py")
        paused = self.board.root / "first-read"
        release = self.board.root / "release-first"
        attempted = self.board.root / "second-attempt"
        first = self.start(self.worker_args("first"), hook="story_path", marker=paused,
                           release=release)
        self.wait_for(paused, first)
        self.assert_board_lock_held()
        second = self.start(self.worker_args("second"), attempted=attempted)
        self.wait_for(attempted, second)
        release.write_text("continue")
        self.finish(first)
        self.finish(second)
        story = self.board.story(1)
        self.assertEqual({"first", "second"}, set(story["receipts"]))
        self.assertEqual(["first finding", "second finding"],
                         [entry["text"] for entry in story["findings"]])
        projected = next(story for story in self.board.roadmap()["stories"] if story["id"] == 1)
        self.assertEqual(story["receipts"], projected["receipts"])

    def test_epic_cancellation_waits_for_worker_then_preserves_its_evidence(self):
        self.board.make_ready(1, "worker", "src/state.py")
        paused = self.board.root / "worker-read"
        release = self.board.root / "release-worker"
        attempted = self.board.root / "cancel-attempt"
        worker = self.start(self.worker_args("completed", review=True), hook="story_path",
                            marker=paused, release=release)
        self.wait_for(paused, worker)
        self.assert_board_lock_held()
        cancel = self.start(["epic", "--epic", "1", "--actor", "human",
                             "--status", "cancelled", "--decision", "D-CANCEL"],
                            attempted=attempted)
        self.wait_for(attempted, cancel)
        release.write_text("continue")
        self.finish(worker)
        self.finish(cancel)
        story = self.board.story(1)
        self.assertEqual("cancelled", story["status"])
        self.assertIn("completed", story["receipts"])
        self.assertEqual(["in-review", "cancelled"], [entry["to"] for entry in story["history"][-2:]])
        self.assertEqual("cancelled", self.board.epic_record(1)["status"])

    def test_worker_waiting_on_epic_cancellation_cannot_resurrect_frozen_story(self):
        self.board.make_ready(1, "worker", "src/state.py")
        paused = self.board.root / "cancel-read"
        release = self.board.root / "release-cancel"
        attempted = self.board.root / "worker-attempt"
        cancel = self.start(["epic", "--epic", "1", "--actor", "human",
                             "--status", "cancelled", "--decision", "D-CANCEL"],
                            hook="load_board", marker=paused, release=release)
        self.wait_for(paused, cancel)
        self.assert_board_lock_held()
        worker = self.start(self.worker_args("stale", review=True), attempted=attempted)
        self.wait_for(attempted, worker)
        release.write_text("continue")
        self.finish(cancel)
        self.assertIn("frozen history", self.finish(worker, expected=2))
        story = self.board.story(1)
        self.assertEqual("cancelled", story["status"])
        self.assertEqual("cancelled", story["history"][-1]["to"])
        self.assertNotIn("stale", story["receipts"])
        frozen = self.board.story_file(1).read_bytes()
        result = self.board.update(1, "--actor", "orchestrator", "--finding", "late finding")
        self.assertEqual(2, result.returncode)
        self.assertEqual(frozen, self.board.story_file(1).read_bytes())

    def assert_frontier_suppressed(self):
        before = {path: path.read_bytes() for path in self.board.dir().glob("stories/*.json")}
        result = self.board.build()
        self.assertEqual(0, result.returncode, result.stderr)
        document = self.board.roadmap()
        self.assertEqual([], document["frontier"]["ready"])
        self.assertFalse(any(story["state"] == "ready" for story in document["stories"]))
        self.assertTrue(any(problem.get("file") == "active.json" for problem in document["problems"]))
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_broken_existing_pointer_suppresses_frontier_and_readiness(self):
        pointer = self.board.ws.pointer_file()
        before = pointer.read_bytes()
        variants = [
            "{", "[]", json.dumps({"version": 2, "run": ".software-factory/runs/demo/run.json"}),
            json.dumps({"version": 1, "run": None}),
            json.dumps({"version": 1, "run": ".software-factory/runs/absent/run.json"}),
            json.dumps({"version": 1, "run": "../outside/run.json"}),
        ]
        for content in variants:
            with self.subTest(content=content):
                pointer.write_text(content)
                self.assert_frontier_suppressed()
                self.assertEqual(content, pointer.read_text())
        pointer.write_bytes(before)
        self.assertEqual(0, self.board.build().returncode)
        self.assertTrue(self.board.roadmap()["frontier"]["ready"])

    def test_existing_pointer_directory_and_dangling_link_are_broken_authority(self):
        pointer = self.board.ws.pointer_file()
        pointer.unlink()
        pointer.mkdir()
        self.assert_frontier_suppressed()
        pointer.rmdir()
        pointer.symlink_to(self.board.root / "absent.json")
        self.assert_frontier_suppressed()
        self.assertTrue(pointer.is_symlink())

    def test_invalid_run_or_claims_suppress_frontier_without_repairing_state(self):
        run = self.board.ws.run_file()
        original = json.loads(run.read_text())
        variants = [
            "{", json.dumps({**original, "version": 2}),
            json.dumps({**original, "claims": []}),
            json.dumps({**original, "claims": {"1": "invalid"}}),
            json.dumps({**original, "claims": {"1": {"owner": "worker"}}}),
            " " * (roadmap.state_module().MAX_RUN_BYTES + 1),
        ]
        for index, content in enumerate(variants):
            with self.subTest(variant=index):
                run.write_text(content)
                self.assert_frontier_suppressed()
                self.assertEqual(content, run.read_text())

    def test_unreadable_claim_authority_remains_visible_and_suppresses_readiness(self):
        with mock.patch.object(roadmap.state_module(), "load",
                               side_effect=PermissionError("private diagnostic fixture")):
            config = roadmap.board_config(self.board.root)
            document = roadmap.compute_roadmap(self.board.root, config, self.board.dir())
        self.assertEqual([], document["frontier"]["ready"])
        self.assertFalse(any(story["state"] == "ready" for story in document["stories"]))
        problem = next(item for item in document["problems"] if item.get("file") == "active.json")
        self.assertIn("unreadable", problem["reason"])
        self.assertNotIn("private diagnostic fixture", problem["reason"])

    def test_invalid_claim_cannot_authorize_worker_record_mutation(self):
        self.board.make_ready(1, "worker", "src/state.py")
        run = self.board.ws.run_file()
        data = json.loads(run.read_text())
        del data["claims"]["1"]["identity"]
        run.write_text(json.dumps(data))
        before = self.board.story_file(1).read_bytes()
        result = self.board.update(1, "--actor", "worker", "--owner", "worker",
                                   "--finding", "must not be written")
        self.assertEqual(2, result.returncode)
        self.assertIn("claims state", result.stderr)
        self.assertEqual(before, self.board.story_file(1).read_bytes())

    def test_absent_active_program_keeps_normal_frontier_with_historical_runs_present(self):
        self.board.ws.pointer_file().unlink()
        before = self.board.ws.run_file().read_bytes()
        self.assertEqual(0, self.board.build().returncode)
        document = self.board.roadmap()
        self.assertEqual([1], [entry["id"] for entry in document["frontier"]["ready"]])
        self.assertEqual("ready", next(story for story in document["stories"] if story["id"] == 1)["state"])
        self.assertFalse(any(problem.get("file") == "active.json" for problem in document["problems"]))
        self.assertEqual(before, self.board.ws.run_file().read_bytes())


if __name__ == "__main__":
    unittest.main()
