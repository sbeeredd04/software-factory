"""Board kernel tests: per-story records, the roadmap projection, the dashboard.

Covers the VAL-ROADMAP and VAL-WORKSTREAM-001 contract areas: records as the
single live story-status store, one writer per record with ownership enforced
in code, locked revision-stamped regenerable projections, dependency-graph
readiness with cross-stream diagnostics, and claims mirrored read-only.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import unittest

import support

SCRIPTS = support.SCRIPTS
SCHEMA_FILE = support.REPO / "skills" / "software-factory" / "schemas" / "board.schema.json"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def planning_source():
    """Two streams, two epics, four stories with a cross-stream dependency."""
    return {
        "streams": [
            {"id": "W-core", "title": "Core platform", "status": "active"},
            {"id": "W-app", "title": "Application", "status": "active"},
        ],
        "epics": [
            {
                "key": "kernel",
                "stream": "W-core",
                "title": "Kernel",
                "outcome": "Reliable local state",
                "done_when": ["claims are atomic", "checkpoints bounded"],
                "covers": ["P1"],
                "needs": [],
                "stories": [
                    {"key": "state", "title": "State helper", "type": "story",
                     "after": [], "covers": ["R1"], "risk": "T2",
                     "scope": ["src/state.py"]},
                    {"key": "gate", "title": "Gate helper", "type": "story",
                     "after": ["state"], "covers": ["R2"], "risk": "T1",
                     "scope": ["src/gate.py"]},
                ],
            },
            {
                "key": "ui",
                "stream": "W-app",
                "title": "App UI",
                "outcome": "Usable application",
                "done_when": ["shell renders"],
                "covers": ["P2"],
                "needs": ["kernel"],
                "stories": [
                    {"key": "shell", "title": "App shell", "type": "story",
                     "after": [{"epic": "kernel"}], "covers": ["R3"], "risk": "T1"},
                    {"key": "board", "title": "Board view", "type": "story",
                     "after": ["shell", "kernel/gate"], "covers": ["R4"], "risk": "T2",
                     "sprint": "now"},
                ],
            },
        ],
    }


class Board:
    """A workspace with a git repo (for claims) and board CLI helpers."""

    def __init__(self, test):
        self.ws = support.Workspace()
        test.addCleanup(self.ws.cleanup)
        self.root = self.ws.root
        self.repo = self.ws.repo()

    # -- paths -------------------------------------------------------------
    def dir(self):
        return self.root / ".software-factory" / "context" / "board"

    def roadmap_file(self):
        return self.dir() / "roadmap.json"

    def dashboard_file(self):
        return self.dir() / "dashboard.html"

    def story_file(self, story_id):
        return self.dir() / "stories" / f"{story_id}.json"

    def epic_file(self, epic_id):
        return self.dir() / "epics" / f"{epic_id}.json"

    # -- CLI -----------------------------------------------------------------
    def board(self, *args, env=None):
        return support.run("roadmap", "--workspace", self.root, *args, env=env)

    def derive(self, source=None):
        result = self.derive_raw(source)
        assert result.returncode == 0, result.stderr
        return result

    def derive_raw(self, source=None):
        source = planning_source() if source is None else source
        path = self.root / "plan.json"
        path.write_text(json.dumps(source))
        return self.board("derive", "--source", path)

    def build(self, *args, env=None):
        return self.board("build", *args, env=env)

    def update(self, story, *args):
        # Legacy lifecycle tests receive explicit synthetic gate fixtures.
        # Rejection tests in test_board_gate call board() without this helper.
        if "--status" in args and "--actor" in args and args[args.index("--actor") + 1] == "orchestrator":
            status = args[args.index("--status") + 1]
            if status == "built" and "--sha" not in args:
                args = (*args, "--sha", SHA_A)
            if status in ("built", "done") and "--sha" in args and "--evidence" not in args:
                sha = args[args.index("--sha") + 1]
                phase = "premerge" if status == "built" else "complete"
                args = (*args, "--evidence", self.gate_manifest(story, sha, phase))
        return self.board("update", "--story", str(story), *args)

    def gate_manifest(self, story, sha, phase):
        directory = self.root / "proof"
        directory.mkdir(exist_ok=True)
        artifact = directory / f"{story}-{phase}.txt"
        artifact.write_text("Synthetic fixture evidence; no actual effect claimed.\n")
        names = ("tests", "eval", "review", "ci") + (("deploy",) if phase == "complete" else ())
        checks = {name: {"status": "pass", "subject_sha": sha,
                         "artifact": artifact.relative_to(self.root).as_posix(),
                         "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                         "exit_code": 0} for name in names}
        record = self.story(story)
        report = {"subject_sha": sha, "author": record.get("owner") or "worker",
                  "reviewer": "independent-reviewer", "checks": checks}
        if phase == "complete":
            candidate = record.get("accepted_gates", {}).get("premerge", {}).get("subject_sha", SHA_A)
            report.update(candidate_sha=candidate,
                          integration={"status": "pass", "subject_sha": sha, "candidate_sha": candidate})
            checks["deploy"].update(deployed_sha=sha, artifact_id="fixture-artifact", environment="fixture")
        manifest = directory / f"{story}-{phase}.json"
        manifest.write_text(json.dumps(report))
        return manifest.relative_to(self.root).as_posix()

    def epic(self, epic, *args):
        if ("--actor" in args and args[args.index("--actor") + 1] == "human"
                and "--status" in args and args[args.index("--status") + 1] == "done"
                and "--decision" not in args and self.epic_record(epic)["status"] == "awaiting-acceptance"):
            args = (*args, "--decision", self.epic_approval(epic))
        return self.board("epic", "--epic", str(epic), *args)

    def epic_approval(self, epic):
        """Synthetic independent outcome/owner fixtures, never real acceptance."""
        module = support.helper("roadmap")
        digest, children, _ = module.epic_review_scope(self.root, module.board_config(self.root), self.epic_record(epic))
        legacy = [story["id"] for story in children
                  if story["status"] == "done" and not story.get("accepted_gates", {}).get("complete")]
        bundle = self.root / f"epic-{epic}-review.json"
        bundle.write_text(json.dumps({"status": "pass", "scope_sha256": digest,
                                      "author": "fixture-reconciler", "reviewer": "fixture-independent",
                                      "legacy_children": legacy}))
        source = self.root / f"epic-{epic}-owner.txt"
        source.write_text("Synthetic owner approval; not an authenticated decision.\n")
        approval = {"decision": "approve", "scope": {"epic": epic}, "phase": "epic",
                    "scope_sha256": digest, "approved_by": "fixture-owner", "approved_at": "2026-10-15T00:00:00Z",
                    "legacy_children": legacy,
                    "source": {"kind": "user-conversation", "ref": "fixture:epic-owner",
                               "artifact": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                    "evidence": {"artifact": bundle.name, "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}}
        path = self.root / f"epic-{epic}-approval.json"
        path.write_text(json.dumps(approval))
        return path.name

    # -- records -------------------------------------------------------------
    def story(self, story_id):
        return json.loads(self.story_file(story_id).read_text())

    def write_story(self, story_id, **changes):
        path = self.story_file(story_id)
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def epic_record(self, epic_id):
        return json.loads(self.epic_file(epic_id).read_text())

    def roadmap(self):
        return json.loads(self.roadmap_file().read_text())

    def board_snapshot(self):
        """Every file under the board dir, content-keyed, for zero-write proofs."""
        return {
            str(path.relative_to(self.dir())): path.read_bytes()
            for path in sorted(self.dir().rglob("*"))
            if path.is_file()
        }

    def write_meta(self, **changes):
        path = self.dir() / "meta.json"
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def receipt(self, name="receipt.json", sha=SHA_A, **extra):
        path = self.root / name
        path.write_text(json.dumps({"subject_sha": sha, **extra}))
        return path

    def claim(self, story_id, owner, *paths):
        result = self.ws.claim(str(story_id), owner, self.repo, *paths)
        assert result.returncode == 0, result.stderr
        return result

    def make_ready(self, story_id, owner, *paths):
        """Orchestrator ready-for-dev, then claim, then worker in-progress."""
        result = self.update(
            story_id, "--actor", "orchestrator", "--status", "ready-for-dev"
        )
        assert result.returncode == 0, result.stderr
        self.claim(story_id, owner, *paths)
        result = self.update(
            story_id, "--actor", "worker", "--owner", owner, "--status", "in-progress"
        )
        assert result.returncode == 0, result.stderr

    def finish(self, story_id, owner, merge_sha):
        """Drive a claimed in-progress story through review, built and done."""
        receipt = self.receipt(name=f"receipt-{story_id}.json")
        result = self.update(
            story_id, "--actor", "worker", "--owner", owner,
            "--receipt", f"tests={receipt}", "--status", "in-review",
        )
        assert result.returncode == 0, result.stderr
        result = self.update(
            story_id, "--actor", "orchestrator", "--status", "built"
        )
        assert result.returncode == 0, result.stderr
        result = self.ws.run_state("release", "--task", str(story_id), "--owner", owner)
        assert result.returncode == 0, result.stderr
        result = self.update(
            story_id, "--actor", "orchestrator", "--status", "done", "--sha", merge_sha
        )
        assert result.returncode == 0, result.stderr


class SchemaAndLayoutTests(unittest.TestCase):
    def test_shipped_schema_file_covers_the_code_contract(self):
        schema = json.loads(SCHEMA_FILE.read_text())
        story = schema["$defs"]["story"]
        self.assertEqual(
            story["properties"]["status"]["enum"],
            ["backlog", "ready-for-dev", "in-progress", "in-review", "built", "done", "cancelled"],
        )
        for field in ("id", "epic", "type", "title", "status", "after", "covers",
                      "risk", "hitl", "plan_checkpoint", "done_checkpoint",
                      "blocked", "receipts", "history"):
            self.assertIn(field, story["required"])
        blocked = story["properties"]["blocked"]
        self.assertEqual(
            blocked["properties"]["type"]["enum"],
            ["human-decision", "external", "resource-contention", "design"],
        )
        self.assertFalse(blocked["additionalProperties"])
        # Unknown record keys are ignored at read time: records stay extensible.
        self.assertTrue(schema["$defs"]["story"]["additionalProperties"])
        self.assertTrue(schema["$defs"]["epic"]["additionalProperties"])
        epic = schema["$defs"]["epic"]
        self.assertEqual(
            epic["properties"]["status"]["enum"],
            ["planned", "in-progress", "awaiting-acceptance", "done", "parked", "cancelled"],
        )

    def test_helpers_are_stdlib_only(self):
        for name in ("roadmap", "dashboard"):
            self.assertEqual(support.non_stdlib_imports(SCRIPTS / f"{name}.py"), [])

    def test_board_never_invokes_agent_clis(self):
        board = Board(self)
        board.derive()
        env, log, _ = support.guard_env()
        result = board.build(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text() if log.exists() else "", "")


class DeriveTests(unittest.TestCase):
    def test_derive_creates_records_with_stable_integer_ids(self):
        board = Board(self)
        board.derive()
        story = board.story(1)
        self.assertEqual(story["id"], 1)
        self.assertEqual(story["epic"], 1)
        self.assertEqual(story["status"], "backlog")
        self.assertEqual(story["title"], "State helper")
        self.assertEqual(story["after"], [])
        self.assertEqual(story["covers"], ["R1"])
        self.assertEqual(story["scope"], ["src/state.py"])
        self.assertEqual(board.story(4)["after"], [3, 2])
        self.assertEqual(board.story(3)["after"], [{"epic": 1}])
        epic = board.epic_record(2)
        self.assertEqual(epic["needs"], [1])
        self.assertEqual(epic["order"], [3, 4])
        streams = json.loads((board.dir() / "streams.json").read_text())
        self.assertEqual([s["id"] for s in streams["streams"]], ["W-core", "W-app"])
        self.assertEqual(streams["streams"][1]["epics"], [2])

    def test_rederive_joins_by_source_key_and_never_reuses_ids(self):
        board = Board(self)
        board.derive()
        board.update(1, "--actor", "orchestrator", "--status", "cancelled", "--reason", "superseded")
        board.update(1, "--actor", "human", "--status", "cancelled", "--decision", "D-7")
        source = planning_source()
        source["epics"][0]["stories"].append(
            {"key": "hook", "title": "Hook helper", "type": "story",
             "after": [], "covers": ["R5"], "risk": "T0"}
        )
        board.derive(source)
        retained = board.story(1)
        self.assertEqual(retained["title"], "State helper")
        self.assertEqual(retained["status"], "cancelled")  # frozen history untouched
        new = board.story(5)
        self.assertEqual(new["title"], "Hook helper")
        self.assertEqual(new["status"], "backlog")
        meta = json.loads((board.dir() / "meta.json").read_text())
        self.assertEqual(meta["next_story_id"], 6)  # id 2..4 still live, 1 cancelled, none reused

    def test_rederive_refuses_terminal_story_structural_changes_without_writes(self):
        for status in ("done", "cancelled"):
            with self.subTest(status=status):
                board = Board(self)
                board.derive()
                board.write_story(1, status=status)
                source = planning_source()
                source["epics"][0]["stories"][0]["title"] = "Rewritten history"
                before = board.board_snapshot()
                result = board.derive_raw(source)
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertIn("frozen terminal", result.stderr)
                self.assertEqual(before, board.board_snapshot())

    def test_terminal_epic_dangling_order_cannot_authorize_a_new_child(self):
        board = Board(self)
        board.derive()
        epic = board.epic_record(1)
        epic.update(status="done", order=[1, 2, 99])
        board.epic_file(1).write_text(json.dumps(epic))
        board.write_meta(next_story_id=99)
        source = planning_source()
        source["epics"][0]["stories"].append({"key": "late", "title": "Late child"})
        before = board.board_snapshot()
        result = board.derive_raw(source)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("frozen terminal child membership", result.stderr)
        self.assertEqual(before, board.board_snapshot())

        # Even malformed historical open children cannot redefine accepted scope.
        source = planning_source()
        source["epics"][0]["stories"][0]["title"] = "Edited accepted descendant"
        result = board.derive_raw(source)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("frozen terminal", result.stderr)
        self.assertEqual(before, board.board_snapshot())

    def test_unknown_record_keys_are_ignored_at_read_time(self):
        board = Board(self)
        board.derive()
        story = board.story(1)
        story["team_custom"] = {"anything": ["goes"]}
        board.story_file(1).write_text(json.dumps(story, indent=2) + "\n")
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.roadmap()["problems"], [])

    def test_derive_refuses_a_stale_story_counter_and_writes_nothing(self):
        board = Board(self)
        board.derive()
        board.write_meta(next_story_id=1)  # stories 1..4 already exist
        before = board.board_snapshot()
        source = planning_source()
        source["epics"][0]["stories"].append(
            {"key": "hook", "title": "Hook helper", "type": "story",
             "after": [], "covers": ["R5"], "risk": "T0"}
        )
        result = board.derive_raw(source)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("board:"), result.stderr)
        self.assertIn("next_story_id", result.stderr)
        self.assertIn("story id 4", result.stderr)  # the true maximum
        self.assertEqual(board.board_snapshot(), before)  # zero files written

    def test_derive_refuses_a_stale_epic_counter_and_writes_nothing(self):
        board = Board(self)
        board.derive()
        board.write_meta(next_epic_id=2)  # epics 1 and 2 already exist
        before = board.board_snapshot()
        # Fail closed even when the source mints nothing new: a stale counter
        # is board drift, and repairing it is an explicit operator action.
        result = board.derive_raw()
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("board:"), result.stderr)
        self.assertIn("next_epic_id", result.stderr)
        self.assertIn("epic id 2", result.stderr)  # the true maximum
        self.assertEqual(board.board_snapshot(), before)

    def test_derive_refuses_a_minted_id_colliding_with_a_record_file(self):
        board = Board(self)
        board.derive()
        # Joins are by id, never by filename: record 4 may live in
        # stories/5.json. The counter (5) exceeds every record id, yet minting
        # id 5 would overwrite that existing file.
        board.story_file(4).rename(board.story_file(5))
        before = board.board_snapshot()
        source = planning_source()
        source["epics"][0]["stories"].append(
            {"key": "hook", "title": "Hook helper", "type": "story",
             "after": [], "covers": ["R5"], "risk": "T0"}
        )
        result = board.derive_raw(source)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("board:"), result.stderr)
        self.assertIn("next_story_id", result.stderr)
        self.assertIn("stories/5.json", result.stderr)
        self.assertEqual(board.board_snapshot(), before)
        self.assertEqual(json.loads(board.story_file(5).read_text())["id"], 4)

    def test_derive_happy_path_after_explicit_counter_repair(self):
        board = Board(self)
        board.derive()
        board.write_meta(next_story_id=1)  # stale; the refusal above applies
        source = planning_source()
        source["epics"][0]["stories"].append(
            {"key": "hook", "title": "Hook helper", "type": "story",
             "after": [], "covers": ["R5"], "risk": "T0"}
        )
        self.assertEqual(board.derive_raw(source).returncode, 2)
        # Repair is an explicit operator action: set the counter above the
        # true maximum, then derive succeeds and mints the next id.
        board.write_meta(next_story_id=5)
        result = board.derive_raw(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.story(5)["title"], "Hook helper")
        self.assertEqual(board.story(1)["title"], "State helper")  # never overwritten
        meta = json.loads((board.dir() / "meta.json").read_text())
        self.assertEqual(meta["next_story_id"], 6)


class TransitionTests(unittest.TestCase):
    def test_full_story_lifecycle_with_history(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        story = board.story(1)
        self.assertEqual(story["status"], "in-progress")
        self.assertEqual(story["owner"], "w1")
        board.finish(1, "w1", SHA_B)
        story = board.story(1)
        self.assertEqual(story["status"], "done")
        self.assertEqual(story["merged_sha"], SHA_B)
        transitions = [(row["from"], row["to"], row["by"]) for row in story["history"]]
        self.assertEqual(
            transitions,
            [
                ("backlog", "ready-for-dev", "orchestrator"),
                ("ready-for-dev", "in-progress", "w1"),
                ("in-progress", "in-review", "w1"),
                ("in-review", "built", "orchestrator"),
                ("built", "done", "orchestrator"),
            ],
        )
        self.assertEqual(story["receipts"]["tests"]["subject_sha"], SHA_A)

    def test_worker_cannot_write_built_or_done(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        for target in ("built", "done"):
            result = board.update(
                1, "--actor", "worker", "--owner", "w1", "--status", target
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("orchestrator", result.stderr)
        self.assertEqual(board.story(1)["status"], "in-progress")

    def test_worker_owner_mismatch_refused(self):
        board = Board(self)
        board.derive()
        board.update(1, "--actor", "orchestrator", "--status", "ready-for-dev")
        board.claim(1, "w1", "src/state.py")
        result = board.update(1, "--actor", "worker", "--owner", "w2", "--status", "in-progress")
        self.assertEqual(result.returncode, 2)
        self.assertIn("owner", result.stderr)
        self.assertEqual(board.story(1)["status"], "ready-for-dev")

    def test_worker_without_claim_refused(self):
        board = Board(self)
        board.derive()
        board.update(1, "--actor", "orchestrator", "--status", "ready-for-dev")
        result = board.update(1, "--actor", "worker", "--owner", "w1", "--status", "in-progress")
        self.assertEqual(result.returncode, 2)
        self.assertIn("claim", result.stderr)

    def test_in_review_requires_a_receipt_bound_to_a_subject(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        result = board.update(1, "--actor", "worker", "--owner", "w1", "--status", "in-review")
        self.assertEqual(result.returncode, 2)
        self.assertIn("receipt", result.stderr)
        receipt = board.receipt()
        result = board.update(
            1, "--actor", "worker", "--owner", "w1",
            "--receipt", f"tests={receipt}", "--status", "in-review",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_built_requires_providers_done(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        receipt = board.receipt()
        board.update(1, "--actor", "worker", "--owner", "w1",
                     "--receipt", f"tests={receipt}", "--status", "in-review")
        # Story 2 depends on story 1; review counts as met for starting, but
        # built is refused until the provider merges (status done).
        board.make_ready(2, "w2", "src/gate.py")
        board.update(2, "--actor", "worker", "--owner", "w2",
                     "--receipt", f"tests={receipt}", "--status", "in-review")
        result = board.update(2, "--actor", "orchestrator", "--status", "built")
        self.assertEqual(result.returncode, 2)
        self.assertIn("1", result.stderr)
        # Story 1 merges; the dependent's gate transition now succeeds.
        result = board.update(1, "--actor", "orchestrator", "--status", "built")
        self.assertEqual(result.returncode, 0, result.stderr)
        board.ws.run_state("release", "--task", "1", "--owner", "w1")
        result = board.update(1, "--actor", "orchestrator", "--status", "done", "--sha", SHA_B)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = board.update(2, "--actor", "orchestrator", "--status", "built")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_done_requires_merge_sha_and_built(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        result = board.update(1, "--actor", "orchestrator", "--status", "done", "--sha", SHA_B)
        self.assertEqual(result.returncode, 2)
        receipt = board.receipt()
        board.update(1, "--actor", "worker", "--owner", "w1",
                     "--receipt", f"tests={receipt}", "--status", "in-review")
        result = board.update(1, "--actor", "orchestrator", "--status", "built")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = board.update(1, "--actor", "orchestrator", "--status", "done")
        self.assertEqual(result.returncode, 2)
        self.assertIn("sha", result.stderr.lower())

    def test_frozen_terminal_records_refuse_edits(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        board.finish(1, "w1", SHA_B)
        for args in (
            ("--actor", "orchestrator", "--status", "built"),
            ("--actor", "orchestrator", "--block", "design", "--reason", "x",
             "--block-owner", "founder", "--next-action", "y"),
        ):
            result = board.update(1, *args)
            self.assertEqual(result.returncode, 2, args)
            self.assertIn("frozen", result.stderr)
        self.assertEqual(board.story(1)["status"], "done")

    def test_cancel_is_proposed_by_orchestrator_and_confirmed_by_human(self):
        board = Board(self)
        board.derive()
        result = board.update(2, "--actor", "human", "--status", "cancelled", "--decision", "D-1")
        self.assertEqual(result.returncode, 2)  # no proposal yet
        result = board.update(2, "--actor", "worker", "--owner", "w1", "--status", "cancelled")
        self.assertEqual(result.returncode, 2)
        result = board.update(2, "--actor", "orchestrator", "--status", "cancelled",
                              "--reason", "scope cut")
        self.assertEqual(result.returncode, 0, result.stderr)
        story = board.story(2)
        self.assertEqual(story["status"], "backlog")  # proposal does not move status
        self.assertEqual(story["cancel_proposal"]["reason"], "scope cut")
        result = board.update(2, "--actor", "human", "--status", "cancelled", "--decision", "D-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.story(2)["status"], "cancelled")

    def test_cancelled_story_still_blocks_dependents(self):
        board = Board(self)
        board.derive()
        board.update(1, "--actor", "orchestrator", "--status", "cancelled", "--reason", "cut")
        board.update(1, "--actor", "human", "--status", "cancelled", "--decision", "D-2")
        board.build()
        roadmap = board.roadmap()
        waiting = {entry["id"]: entry for entry in roadmap["frontier"]["waiting_on_prereq"]}
        self.assertIn(2, waiting)
        self.assertTrue(any("cancelled" in item for item in waiting[2]["missing"]))
        ready_ids = [entry["id"] for entry in roadmap["frontier"]["ready"]]
        self.assertNotIn(2, ready_ids)

    def test_blocked_overlay_rules(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        result = board.update(
            1, "--actor", "worker", "--owner", "w1", "--block", "dependency",
            "--reason", "waits", "--block-owner", "w1", "--next-action", "wait",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("derived", result.stderr)  # dependency waiting is never stored
        result = board.update(
            1, "--actor", "worker", "--owner", "w1", "--block", "design",
            "--reason", "no approved compact receipt UI",
            "--block-owner", "founder", "--next-action", "approve option A",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        blocked = board.story(1)["blocked"]
        self.assertEqual(blocked["type"], "design")
        self.assertEqual(blocked["owner"], "founder")
        self.assertEqual(blocked["next_action"], "approve option A")
        self.assertTrue(blocked["since"])
        self.assertEqual(board.story(1)["status"], "in-progress")  # overlay, not a status
        result = board.update(1, "--actor", "worker", "--owner", "w1", "--unblock")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(board.story(1)["blocked"])

    def test_findings_append_dated_blocks_without_changing_status(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        result = board.update(1, "--actor", "orchestrator", "--finding", "naming drifts")
        self.assertEqual(result.returncode, 0, result.stderr)
        story = board.story(1)
        self.assertEqual(story["status"], "in-progress")
        self.assertEqual(story["findings"][-1]["text"], "naming drifts")
        self.assertTrue(story["findings"][-1]["at"])

    def test_epic_lifecycle_and_human_acceptance(self):
        board = Board(self)
        board.derive()
        result = board.epic(1, "--actor", "human", "--status", "done")
        self.assertEqual(result.returncode, 2)  # only from awaiting-acceptance
        result = board.epic(1, "--actor", "orchestrator", "--status", "awaiting-acceptance")
        self.assertEqual(result.returncode, 2)  # stories not done yet
        board.make_ready(1, "w1", "src/state.py")
        board.finish(1, "w1", SHA_B)
        board.make_ready(2, "w2", "src/gate.py")
        board.finish(2, "w2", SHA_C)
        result = board.epic(1, "--actor", "orchestrator", "--status", "awaiting-acceptance")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = board.epic(1, "--actor", "orchestrator", "--status", "done")
        self.assertEqual(result.returncode, 2)  # humans accept epics
        result = board.epic(1, "--actor", "human", "--status", "done")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.epic_record(1)["status"], "done")

    def test_epic_park_and_cancel(self):
        board = Board(self)
        board.derive()
        result = board.epic(2, "--actor", "human", "--status", "parked")
        self.assertEqual(result.returncode, 2)  # needs a proposal with a resume pointer
        result = board.epic(2, "--actor", "orchestrator", "--status", "parked",
                            "--resume", "branch wip/ui at tip; resume after kernel")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.epic_record(2)["status"], "planned")
        result = board.epic(2, "--actor", "human", "--status", "parked")
        self.assertEqual(result.returncode, 0, result.stderr)
        parked = board.epic_record(2)
        self.assertEqual(parked["status"], "parked")
        self.assertIn("branch wip/ui", parked["parked"]["resume"])
        result = board.epic(2, "--actor", "human", "--status", "cancelled", "--decision", "D-9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.story(3)["status"], "cancelled")
        self.assertEqual(board.story(4)["status"], "cancelled")


class ProjectionTests(unittest.TestCase):
    def test_regeneration_is_byte_identical_without_input_change(self):
        board = Board(self)
        board.derive()
        board.build()
        first = (board.roadmap_file().read_bytes(), board.dashboard_file().read_bytes())
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        second = (board.roadmap_file().read_bytes(), board.dashboard_file().read_bytes())
        self.assertEqual(first, second)
        # A record edit bumps the revision by exactly one; then stability again.
        before = board.roadmap()["revision"]
        board.update(1, "--actor", "orchestrator", "--status", "ready-for-dev")
        self.assertEqual(board.roadmap()["revision"], before + 1)
        again = (board.roadmap_file().read_bytes(), board.dashboard_file().read_bytes())
        board.build()
        self.assertEqual(again, (board.roadmap_file().read_bytes(),
                                 board.dashboard_file().read_bytes()))

    def test_rebuild_from_scratch_restores_both_artifacts(self):
        board = Board(self)
        board.derive()
        board.build()
        original_json = board.roadmap_file().read_text()
        original_html = board.dashboard_file().read_text()
        board.roadmap_file().unlink()
        board.dashboard_file().unlink()
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        # Identical apart from the generation timestamp and the revision counter.
        mask = lambda text: re.sub(
            r'"revision": \d+|"generated_at": "[^"]+"', '"STABLE"', text
        )
        self.assertEqual(mask(original_json), mask(board.roadmap_file().read_text()))
        mask_html = lambda text: re.sub(
            r"revision \d+ · generated [^·]+", "revision N", text
        )
        self.assertEqual(mask_html(original_html), mask_html(board.dashboard_file().read_text()))

    def test_tampered_projection_is_overwritten(self):
        board = Board(self)
        board.derive()
        board.build()
        tampered = board.roadmap()
        tampered["stories"][0]["title"] = "hand edited"
        board.roadmap_file().write_text(json.dumps(tampered, indent=2) + "\n")
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        titles = [s["title"] for s in board.roadmap()["stories"]]
        self.assertNotIn("hand edited", titles)
        self.assertIn("State helper", titles)

    def test_degenerate_record_is_a_problem_not_a_crash(self):
        board = Board(self)
        board.derive()
        board.write_story(2, status="mystery")
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        roadmap = board.roadmap()
        problems = " ".join(p["reason"] for p in roadmap["problems"])
        self.assertIn("mystery", problems)
        states = {s["id"]: s["state"] for s in roadmap["stories"]}
        self.assertEqual(states[1], "ready")  # the healthy stories still derive
        self.assertNotIn(2, states)

    def test_cycle_is_rejected_loudly_and_never_rendered(self):
        board = Board(self)
        board.derive()
        board.write_story(1, after=[2])
        board.roadmap_file().unlink()  # prove the failed build writes nothing new
        board.dashboard_file().unlink()
        result = board.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cycle", result.stderr.lower())
        self.assertIn("1", result.stderr)
        self.assertIn("2", result.stderr)
        self.assertFalse(board.roadmap_file().exists())
        self.assertFalse(board.dashboard_file().exists())

    def test_projection_write_failure_leaves_records_intact(self):
        board = Board(self)
        board.derive()
        board.build()
        board.roadmap_file().unlink()
        board.roadmap_file().mkdir()  # the projection path is now unwritable
        before = board.story_file(1).read_bytes()
        result = board.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(board.story_file(1).read_bytes(), before)
        board.roadmap_file().rmdir()
        self.assertEqual(board.build().returncode, 0)

    def test_generated_banner_and_config(self):
        board = Board(self)
        board.derive()
        roadmap = board.roadmap()
        self.assertEqual(roadmap["version"], 1)
        self.assertIn("generated_at", roadmap)
        self.assertIn("revision", roadmap)
        banner = json.dumps(roadmap["generated"])
        self.assertIn("do not hand-edit", banner)
        self.assertIn("roadmap.py build", banner)
        html = board.dashboard_file().read_text()
        self.assertIn("do not hand-edit", html)
        self.assertIn("roadmap.py build", html)

    def test_config_board_keys_are_read(self):
        board = Board(self)
        config = {"board": {"dir": ".software-factory/context/board", "regenerate": "manual"}}
        (board.root / ".software-factory" / "config.yaml").write_text(json.dumps(config))
        board.derive()
        self.assertFalse(board.roadmap_file().exists())  # manual policy: no auto-build
        board.build()
        board.update(1, "--actor", "orchestrator", "--status", "ready-for-dev")
        # regenerate: manual — the record write did not rebuild the projection.
        roadmap = board.roadmap()
        states = {s["id"]: s["status"] for s in roadmap["stories"]}
        self.assertEqual(states[1], "backlog")
        board.build()
        states = {s["id"]: s["status"] for s in board.roadmap()["stories"]}
        self.assertEqual(states[1], "ready-for-dev")

    def test_custom_board_directory_from_config(self):
        board = Board(self)
        config = {"board": {"dir": ".software-factory/context/alt-board"}}
        (board.root / ".software-factory" / "config.yaml").write_text(json.dumps(config))
        board.derive()
        self.assertTrue(
            (board.root / ".software-factory" / "context" / "alt-board" / "streams.json").is_file()
        )
        self.assertFalse((board.dir() / "streams.json").exists())

    def test_malformed_config_fails_closed(self):
        board = Board(self)
        (board.root / ".software-factory" / "config.yaml").write_text("{ not json")
        result = board.board("init")
        self.assertEqual(result.returncode, 2)
        self.assertIn("config", result.stderr.lower())


class ReadinessTests(unittest.TestCase):
    def test_review_counts_as_met_for_readiness(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        board.build()
        waiting = {e["id"] for e in board.roadmap()["frontier"]["waiting_on_prereq"]}
        self.assertIn(2, waiting)  # in-progress prerequisite is not met
        receipt = board.receipt()
        board.update(1, "--actor", "worker", "--owner", "w1",
                     "--receipt", f"tests={receipt}", "--status", "in-review")
        board.build()
        ready = {e["id"]: e for e in board.roadmap()["frontier"]["ready"]}
        self.assertIn(2, ready)  # in-review counts as met
        self.assertIn("review", ready[2]["why"])

    def test_epic_gate_holds_until_the_human_accepts(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        board.finish(1, "w1", SHA_B)
        board.make_ready(2, "w2", "src/gate.py")
        board.finish(2, "w2", SHA_C)
        board.build()
        # Both stories done, but epic 1 is not human-accepted: the gate holds.
        waiting = {e["id"]: e for e in board.roadmap()["frontier"]["waiting_on_prereq"]}
        self.assertIn(3, waiting)
        self.assertTrue(any("epic" in item for item in waiting[3]["missing"]))
        board.epic(1, "--actor", "orchestrator", "--status", "awaiting-acceptance")
        board.epic(1, "--actor", "human", "--status", "done")
        board.build()
        ready = {e["id"] for e in board.roadmap()["frontier"]["ready"]}
        self.assertIn(3, ready)

    def test_diagnostics_unpinned_undeclared_and_order_conflict(self):
        board = Board(self)
        source = planning_source()
        # Story 4 already waits on kernel/gate; drop the pin from story 3 and
        # keep epic ui's declared need on kernel -> unpinned gate... instead
        # make story 3's after empty so nothing pins the declared gate.
        source["epics"][1]["stories"][0]["after"] = []
        board.derive(source)
        board.build()
        diagnostics = board.roadmap()["diagnostics"]
        # story 4 waits on kernel/gate -> the gate is pinned after all; craft
        # an unpinned gate by removing that link too.
        source["epics"][1]["stories"][1]["after"] = ["shell"]
        board.derive(source)
        board.build()
        diagnostics = board.roadmap()["diagnostics"]
        self.assertTrue(
            any(d["epic"] == 2 and d["needs"] == 1 for d in diagnostics["unpinned_gates"]),
            diagnostics,
        )
        # Undeclared: story waits on an epic its epic does not declare.
        source["epics"][1]["needs"] = []
        source["epics"][1]["stories"][1]["after"] = ["shell", "kernel/gate"]
        board.derive(source)
        board.build()
        diagnostics = board.roadmap()["diagnostics"]
        self.assertTrue(
            any(d["story"] == 4 and d["depends_on"] == 2 for d in diagnostics["undeclared_after"]),
            diagnostics,
        )
        # Order conflict: story order contradicts a declared dependency.
        source["epics"][0]["stories"] = list(reversed(source["epics"][0]["stories"]))
        board.derive(source)
        board.build()
        diagnostics = board.roadmap()["diagnostics"]
        self.assertTrue(
            any(d["epic"] == 1 and d["story"] == 2 for d in diagnostics["order_conflicts"]),
            diagnostics,
        )

    def test_inconsistencies_between_claims_and_records(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        board.ws.run_state("release", "--task", "1", "--owner", "w1")
        board.claim(99, "w9", "README.md")  # claim with no matching story record
        board.claim(3, "w3", "src/state.py")  # story 3 scope is undeclared... use story 1
        board.build()
        roadmap = board.roadmap()
        kinds = {(i["kind"], i.get("story", i.get("task"))) for i in roadmap["diagnostics"]["inconsistencies"]}
        self.assertIn(("in-progress-without-claim", 1), kinds)
        self.assertIn(("claim-without-record", "99"), kinds)

    def test_claim_paths_outside_story_scope_flagged(self):
        board = Board(self)
        board.derive()
        board.claim(1, "w1", "src/state.py", "src/other.py")
        board.update(1, "--actor", "orchestrator", "--status", "ready-for-dev")
        board.build()
        roadmap = board.roadmap()
        kinds = [i["kind"] for i in roadmap["diagnostics"]["inconsistencies"]]
        self.assertIn("claim-outside-scope", kinds)

    def test_claims_are_mirrored_read_only(self):
        board = Board(self)
        board.derive()
        board.claim(1, "w1", "src/state.py")
        run_file = board.ws.run_file()
        before = run_file.read_bytes()
        result = board.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_file.read_bytes(), before)
        story = next(s for s in board.roadmap()["stories"] if s["id"] == 1)
        self.assertTrue(story["claim"]["live"])
        self.assertEqual(story["claim"]["owner"], "w1")
        self.assertEqual(story["claim"]["paths"], ["src/state.py"])


class WorkstreamTests(unittest.TestCase):
    def test_several_streams_and_stories_in_flight_on_one_board(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")  # W-core in progress
        board.make_ready(3, "w3", "src/shell.py")  # W-app in progress (gate unmet, still workable claim)
        board.build()
        roadmap = board.roadmap()
        self.assertEqual(len(roadmap["streams"]), 2)
        streams = {s["id"]: s for s in roadmap["streams"]}
        self.assertEqual(streams["W-core"]["counts"]["in-progress"], 1)
        self.assertEqual(streams["W-app"]["counts"]["in-progress"], 1)
        states = {s["id"]: s["state"] for s in roadmap["stories"]}
        self.assertEqual(states[1], "in-progress")
        self.assertEqual(states[3], "in-progress")
        # blocked-by inversion crosses streams: story 3 directly blocks story 4,
        # and story 2 (W-core) also blocks story 4 (W-app).
        blocks = {s["id"]: s["blocks"] for s in roadmap["stories"]}
        self.assertIn(4, blocks[3])
        self.assertIn(4, blocks[2])
        self.assertIn(2, blocks[1])
        # the cross-stream dependency is listed as a waiting reason
        waiting = {e["id"]: e for e in roadmap["frontier"]["waiting_on_prereq"]}
        self.assertIn(4, waiting)
        html = board.dashboard_file().read_text()
        self.assertIn("W-core", html)
        self.assertIn("W-app", html)
        self.assertIn('id="stream-W-core"', html)
        self.assertIn('id="frontier"', html)
        self.assertIn('id="blockers"', html)
        self.assertIn("now", html)  # the sprint tag renders as a badge

    def test_no_sprint_entity_only_a_tag(self):
        board = Board(self)
        board.derive()
        roadmap = board.roadmap()
        self.assertNotIn("sprints", roadmap)
        story4 = next(s for s in roadmap["stories"] if s["id"] == 4)
        self.assertEqual(story4["sprint"], "now")

    def test_blockers_panel_age_sorted_with_stalled_chain(self):
        board = Board(self)
        board.derive()
        board.update(1, "--actor", "orchestrator", "--block", "human-decision",
                     "--reason", "pick the eval harness", "--block-owner", "founder",
                     "--next-action", "choose option B")
        board.update(3, "--actor", "orchestrator", "--block", "external",
                     "--reason", "waiting on registry", "--block-owner", "vendor",
                     "--next-action", "retry tomorrow")
        # Age the second blocker backwards so ordering is deterministic.
        story3 = board.story(3)
        story3["blocked"]["since"] = "2026-01-01T00:00:00+00:00"
        board.story_file(3).write_text(json.dumps(story3, indent=2) + "\n")
        board.build()
        roadmap = board.roadmap()
        self.assertEqual([b["id"] for b in roadmap["blockers"]], [3, 1])
        blocker1 = next(b for b in roadmap["blockers"] if b["id"] == 1)
        self.assertIn(2, blocker1["stalls"])  # story 2 waits on story 1
        html = board.dashboard_file().read_text()
        self.assertLess(html.index("waiting on registry"), html.index("pick the eval harness"))
        self.assertIn("choose option B", html)
        queue = roadmap["decision_queue"]
        self.assertTrue(any("eval harness" in entry["question"] for entry in queue))

    def test_critical_path_per_stream(self):
        board = Board(self)
        board.derive()
        board.build()
        roadmap = board.roadmap()
        streams = {s["id"]: s for s in roadmap["streams"]}
        self.assertEqual(streams["W-core"]["critical_path"], [1, 2])
        self.assertEqual(streams["W-app"]["critical_path"], [3, 4])


class DashboardTests(unittest.TestCase):
    def test_dashboard_is_static_offline_and_complete(self):
        board = Board(self)
        board.derive()
        board.make_ready(1, "w1", "src/state.py")
        board.finish(1, "w1", SHA_B)
        board.build()
        html = board.dashboard_file().read_text()
        for section in ("frontier", "streams", "blockers", "critical-path",
                        "acceptance", "diagnostics", "problems", "decisions"):
            self.assertIn(f'id="{section}"', html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script", html)
        self.assertIn(SHA_B, html)  # merge SHA receipt on the story card
        self.assertIn(SHA_A[:12], html)  # subject SHA of the tests receipt
        self.assertIn("claims are atomic", html)  # epic done-when checklist

    def test_dashboard_escapes_record_content(self):
        board = Board(self)
        source = planning_source()
        source["epics"][0]["stories"][0]["title"] = "State <script>alert(1)</script> helper"
        board.derive(source)
        board.build()
        html = board.dashboard_file().read_text()
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_single_owner_record_updates(self):
        board = Board(self)
        source = planning_source()
        for index in range(4, 8):
            source["epics"][0]["stories"].append(
                {"key": f"extra-{index}", "title": f"Extra {index}", "type": "story",
                 "after": [], "covers": [], "risk": "T0"}
            )
        board.derive(source)
        owners = {}
        for story_id in range(5, 9):
            owner = f"w{story_id}"
            owners[story_id] = owner
            board.update(story_id, "--actor", "orchestrator", "--status", "ready-for-dev")
            board.claim(story_id, owner, f"src/extra-{story_id}.py")
        results = {}

        def work(story_id):
            results[story_id] = board.update(
                story_id, "--actor", "worker", "--owner", owners[story_id],
                "--status", "in-progress",
            )

        threads = [threading.Thread(target=work, args=(story_id,)) for story_id in owners]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for story_id, result in results.items():
            self.assertEqual(result.returncode, 0, f"story {story_id}: {result.stderr}")
            self.assertEqual(board.story(story_id)["status"], "in-progress")
            history = board.story(story_id)["history"]
            self.assertEqual(history[-1]["to"], "in-progress")
        leftovers = list(board.dir().rglob(".factory-*"))
        self.assertEqual(leftovers, [])
        self.assertEqual(board.build().returncode, 0)
        roadmap = board.roadmap()
        in_progress = [s["id"] for s in roadmap["stories"] if s["state"] == "in-progress"]
        self.assertEqual(sorted(in_progress), [5, 6, 7, 8])

    def test_concurrent_builds_serialize_on_the_board_lock(self):
        board = Board(self)
        board.derive()
        results = []

        def work():
            results.append(board.build())

        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(all(result.returncode == 0 for result in results))
        roadmap = board.roadmap()
        self.assertEqual(len(roadmap["stories"]), 4)


if __name__ == "__main__":
    unittest.main()
