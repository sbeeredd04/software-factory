"""New protected transitions consume real gate validation, not status labels.

All effect/approval fixtures are synthetic structural evidence; no external
integration, authenticated authority or deployment is asserted by these tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import types
import unittest
from pathlib import Path
from unittest import mock

import support
from test_board import SHA_A, SHA_B, SHA_C, Board, planning_source

roadmap = support.helper("roadmap")


class BoardGateTests(unittest.TestCase):
    def setUp(self):
        self.board = Board(self)
        self.board.derive()
        self.board.make_ready(1, "worker", "src/state.py")
        receipt = self.board.receipt()
        result = self.raw("worker", "in-review", "--owner", "worker", "--receipt", f"tests={receipt}")
        self.assertEqual(0, result.returncode, result.stderr)

    def raw(self, actor, status, *args):
        return self.board.board("update", "--story", "1", "--actor", actor,
                                "--status", status, *args)

    def manifest(self, phase="premerge", sha=SHA_A):
        path = self.board.gate_manifest(1, sha, phase)
        return self.board.root / path

    def write(self, path, data):
        path.write_text(json.dumps(data))

    def accept(self, phase="premerge", sha=SHA_A, path=None, *extra):
        path = path or self.manifest(phase, sha)
        return self.raw("orchestrator", "built" if phase == "premerge" else "done",
                        "--sha", sha, "--evidence", path.relative_to(self.board.root).as_posix(), *extra)

    def refused(self, operation, text=None):
        before = self.board.board_snapshot()
        result = operation()
        self.assertEqual(2, result.returncode, result.stderr)
        if text:
            self.assertIn(text, result.stderr)
        self.assertEqual(before, self.board.board_snapshot(), "rejection changed story or projections")
        return result

    def approval(self, phase, *, scope=True, sha=SHA_A):
        record = self.board.story(1)
        source = self.board.root / f"{phase}-owner.txt"
        source.write_text("Synthetic owner approval fixture, not an authenticated user decision.\n")
        decision = {"decision": "approve", "scope": {"story": 1}, "phase": phase,
                    "approved_by": "fixture-owner", "approved_at": "2026-10-15T00:00:00Z",
                    "source": {"kind": "user-conversation", "ref": "fixture:turn-1",
                               "artifact": source.name,
                               "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
        decision["scope_sha256" if scope else "subject_sha"] = roadmap.scope_digest(record) if scope else sha
        path = self.board.root / f"{phase}-decision.json"
        self.write(path, decision)
        return path

    def test_built_and_done_record_manifest_identity_and_current_subjects(self):
        premerge = self.manifest()
        self.assertEqual(0, self.accept(path=premerge).returncode)
        built = self.board.story(1)["accepted_gates"]["premerge"]
        self.assertEqual(hashlib.sha256(premerge.read_bytes()).hexdigest(), built["sha256"])
        complete = self.manifest("complete", SHA_B)
        result = self.accept("complete", SHA_B, complete)
        self.assertEqual(0, result.returncode, result.stderr)
        record = self.board.story(1)
        self.assertEqual("done", record["status"])
        self.assertEqual(SHA_B, record["merged_sha"])
        self.assertEqual(SHA_A, record["accepted_gates"]["premerge"]["subject_sha"])
        self.assertEqual(SHA_B, record["accepted_gates"]["complete"]["subject_sha"])

    def test_missing_short_unknown_and_stale_subjects_are_zero_write_refusals(self):
        for arguments in ((), ("--sha", "short"), ("--sha", "unknown"), ("--sha", SHA_B)):
            with self.subTest(arguments=arguments):
                self.refused(lambda arguments=arguments: self.raw("orchestrator", "built", *arguments))

    def test_failure_statuses_and_missing_checks_never_advance(self):
        path = self.manifest()
        original = json.loads(path.read_text())
        for status in ("fail", "unknown", "unverified", "skipped", "infra_error"):
            report = json.loads(json.dumps(original))
            report["checks"]["tests"]["status"] = status
            self.write(path, report)
            self.refused(lambda path=path: self.accept(path=path))
        original["checks"].pop("ci")
        self.write(path, original)
        self.refused(lambda: self.accept(path=path))

    def test_independent_reviewer_must_differ_from_actual_owner(self):
        path = self.manifest()
        for changes in ({"reviewer": "worker"}, {"author": "different-author"},
                        {"author": 1, "reviewer": 2}):
            path = self.manifest()
            report = json.loads(path.read_text())
            report.update(changes)
            self.write(path, report)
            self.refused(lambda path=path: self.accept(path=path))

    def test_missing_tampered_oversized_or_symlink_artifacts_are_refused(self):
        path = self.manifest()
        artifact = self.board.root / json.loads(path.read_text())["checks"]["tests"]["artifact"]
        artifact.write_text("tampered")
        self.refused(lambda: self.accept(path=path))
        artifact.unlink()
        self.refused(lambda: self.accept(path=path))
        artifact.symlink_to(self.board.repo / "README.md")
        self.refused(lambda: self.accept(path=path))
        artifact.unlink()
        artifact.write_bytes(b"x" * (1024 * 1024 + 1))
        self.refused(lambda: self.accept(path=path))

    def test_escape_symlink_and_oversized_manifest_are_refused(self):
        self.refused(lambda: self.raw("orchestrator", "built", "--sha", SHA_A,
                                     "--evidence", "../outside.json"))
        path = self.manifest()
        linked = self.board.root / "linked.json"
        linked.symlink_to(path)
        self.refused(lambda: self.accept(path=linked))
        path.write_bytes(b" " * (1024 * 1024 + 1))
        self.refused(lambda: self.accept(path=path))

    def test_ambiguous_manifest_receipt_and_decision_json_never_advance(self):
        path = self.manifest()
        original = path.read_bytes()
        path.write_bytes(original[:-1] + b',"author":"worker","value":NaN}')
        self.refused(lambda: self.accept(path=path))
        path.write_bytes(original)
        artifact = self.board.root / "proof/ambiguous.json"
        artifact.write_text('{"verdict":"fail","verdict":"pass"}')
        report = json.loads(original)
        report["checks"]["eval"].update(artifact="proof/ambiguous.json",
                                       artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.write(path, report)
        self.refused(lambda: self.accept(path=path))
        path.write_bytes(original)
        self.board.write_story(1, plan_checkpoint=True)
        approval = self.approval("plan")
        decision = approval.read_bytes()
        approval.write_bytes(b'{"decision":"revoke",' + decision[1:])
        self.refused(lambda: self.accept("premerge", SHA_A, path, "--decision", approval.name))

    def test_renamed_and_encoded_failed_receipts_never_become_opaque_proof(self):
        for suffix in ("txt", "JSON"):
            for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32", "utf-16-be", "utf-32-be"):
                with self.subTest(suffix=suffix, encoding=encoding):
                    path = self.manifest()
                    receipt = self.board.root / f"proof/failed.{suffix}"
                    receipt.write_bytes('{"verdict":"fail"}'.encode(encoding))
                    report = json.loads(path.read_text())
                    report["checks"]["eval"].update(artifact=f"proof/failed.{suffix}",
                                                   artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
                    self.write(path, report)
                    self.refused(lambda path=path: self.accept(path=path))

    def test_renamed_receipt_status_must_explicitly_mean_pass(self):
        for status in ("failed", "pending-review", "pass-executed-cases", None, True):
            with self.subTest(status=status):
                path = self.manifest()
                receipt = self.board.root / "proof/status.txt"
                self.write(receipt, {"status": status})
                report = json.loads(path.read_text())
                report["checks"]["tests"].update(artifact="proof/status.txt",
                                                artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
                self.write(path, report)
                self.refused(lambda path=path: self.accept(path=path))

    def test_boolean_scope_does_not_equal_integer_story_id(self):
        self.board.write_story(1, done_checkpoint=True)
        self.assertEqual(0, self.accept().returncode)
        approval = self.approval("complete")
        decision = json.loads(approval.read_text())
        decision["scope"] = {"story": True}
        self.write(approval, decision)
        path = self.manifest("complete", SHA_B)
        self.refused(lambda: self.accept("complete", SHA_B, path, "--decision", approval.name))

    def test_config_weakening_cannot_discard_premerge_obligations(self):
        self.assertEqual(0, self.accept().returncode)
        config = self.board.root / ".software-factory/config.yaml"
        config.write_text(json.dumps({"verification": {"required_checks": ["review"]}}))
        complete = self.manifest("complete", SHA_B)
        (self.board.root / "proof/1-premerge.txt").write_text("tampered previously required test proof")
        self.refused(lambda: self.accept("complete", SHA_B, complete), "premerge evidence changed")

    def test_initial_board_reads_reject_links_fifos_and_oversize_before_writes(self):
        manifest = self.manifest()
        targets = [self.board.story_file(1), self.board.story_file(2), self.board.epic_file(1),
                   self.board.dir() / "streams.json", self.board.dir() / "meta.json",
                   self.board.roadmap_file(), self.board.dashboard_file()]
        for target in targets:
            saved = target.read_bytes()
            outside = self.board.root / "outside-record"
            outside.write_bytes(saved)
            for kind in ("symlink", "fifo"):
                with self.subTest(target=target.name, kind=kind):
                    target.unlink()
                    if kind == "symlink":
                        target.symlink_to(outside)
                    else:
                        os.mkfifo(target)
                    try:
                        self.refused(lambda: support.run(
                            "roadmap", "--workspace", self.board.root, "update", "--story", "1",
                            "--actor", "orchestrator", "--status", "built", "--sha", SHA_A,
                            "--evidence", manifest.relative_to(self.board.root), timeout=3))
                        self.assertEqual(saved, outside.read_bytes())
                    finally:
                        target.unlink()
                        target.write_bytes(saved)
        target = self.board.story_file(1)
        saved = target.read_bytes()
        target.write_bytes(b" " * (1024 * 1024 + 1))
        self.refused(lambda: self.accept(path=manifest), "protected board")
        target.write_bytes(saved)
        remaining = [32 * roadmap.gate_module().MAX_EVIDENCE_BYTES - 1]
        with self.assertRaises(roadmap.BoardError):
            roadmap.protected_record(self.board.root, target, budget=remaining)
        self.assertEqual(32 * roadmap.gate_module().MAX_EVIDENCE_BYTES - 1, remaining[0])

    def test_board_directory_alias_is_not_followed_even_inside_workspace(self):
        manifest = self.manifest()
        directory = self.board.dir() / "stories"
        actual = self.board.root / "saved-stories"
        directory.rename(actual)
        directory.symlink_to(actual, target_is_directory=True)
        try:
            before = {path.name: path.read_bytes() for path in actual.glob("*.json")}
            self.refused(lambda: self.accept(path=manifest), "protected board")
            self.assertEqual(before, {path.name: path.read_bytes() for path in actual.glob("*.json")})
        finally:
            directory.unlink()
            actual.rename(directory)

    def test_premerge_scope_changes_require_revision_before_completion(self):
        self.board.write_story(1, done_checkpoint=True)
        self.assertEqual(0, self.accept().returncode)
        accepted = self.board.story(1)["accepted_gates"]["premerge"]
        self.assertEqual(roadmap.scope_digest(self.board.story(1)), accepted["scope_sha256"])
        self.board.write_story(1, done_checkpoint=False)
        self.refused(lambda: self.accept("complete", SHA_B), "scope changed")

    def test_protected_config_first_read_is_bounded_and_no_follow(self):
        config = self.board.root / ".software-factory/config.yaml"
        external = self.board.root / "external-config.json"
        external.write_text('{}')
        config.symlink_to(external)
        self.refused(lambda: self.accept(), "configuration")
        config.unlink()
        config.write_bytes(b" " * (1024 * 1024 + 1))
        self.refused(lambda: self.accept(), "configuration")
        for malformed in (None, [], True, "configuration", 1):
            config.write_text(json.dumps(malformed))
            self.refused(lambda: self.accept(), "configuration")
        config.write_text('{}')
        path = self.manifest()
        original = Path.read_text

        def guarded_read(path, *args, **kwargs):
            self.assertNotEqual(config, path, "protected config used the legacy unbounded reader")
            self.assertFalse(path.is_relative_to(self.board.dir()), "protected board used legacy unbounded reader")
            return original(path, *args, **kwargs)

        args = types.SimpleNamespace(command="update", actor="orchestrator", status="built", story=1,
                                     sha=SHA_A, evidence=path.relative_to(self.board.root).as_posix(),
                                     decision=None, receipt=None, finding=None, unblock=False, block=None)
        with mock.patch.object(Path, "read_text", new=guarded_read):
            record = roadmap.update_story(self.board.root, args)
            roadmap.maybe_build(self.board.root, args._validated_config, protected=True)
        self.assertEqual("built", record["status"])

    def test_receipt_verdict_subject_and_self_hash_are_verified(self):
        path = self.manifest()
        artifact = self.board.root / "proof/receipt.json"
        for receipt in ({"subject_sha": SHA_B, "verdict": "pass"},
                        {"git_sha": "unknown", "verdict": "pass"},
                        {"subject_sha": SHA_A, "verdict": "fail"},
                        {"status": "infra_error"},
                        {"subject_sha": SHA_A, "verdict": "pass", "self_sha256": "0" * 64}):
            with self.subTest(receipt=receipt):
                self.write(artifact, receipt)
                report = json.loads(path.read_text())
                report["checks"]["eval"].update(artifact="proof/receipt.json",
                                               artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
                self.write(path, report)
                self.refused(lambda: self.accept(path=path))

    def test_changed_premerge_artifact_or_manifest_blocks_completion(self):
        premerge = self.manifest()
        self.assertEqual(0, self.accept(path=premerge).returncode)
        complete = self.manifest("complete", SHA_B)
        artifact = self.board.root / "proof/1-premerge.txt"
        original = artifact.read_bytes()
        artifact.write_text("changed after acceptance")
        self.refused(lambda: self.accept("complete", SHA_B, complete), "premerge evidence changed")
        artifact.write_bytes(original)
        premerge.write_bytes(premerge.read_bytes() + b" ")
        self.refused(lambda: self.accept("complete", SHA_B, complete), "premerge manifest changed")

    def test_unobserved_integration_stale_candidate_and_missing_effect_identity_block_done(self):
        self.assertEqual(0, self.accept().returncode)
        for mutation in ("integration", "candidate", "effect"):
            path = self.manifest("complete", SHA_B)
            report = json.loads(path.read_text())
            if mutation == "integration":
                report["integration"]["status"] = "unknown"
            elif mutation == "candidate":
                report["candidate_sha"] = SHA_C
            else:
                report["checks"]["deploy"].pop("environment")
            self.write(path, report)
            self.refused(lambda path=path: self.accept("complete", SHA_B, path))

    def test_required_checkpoint_reuses_source_bound_scope_then_rejects_tampering(self):
        self.board.write_story(1, plan_checkpoint=True)
        path = self.manifest()
        self.refused(lambda: self.accept(path=path), "checkpoint")
        approval = self.approval("plan")
        result = self.accept("premerge", SHA_A, path, "--decision", approval.name)
        self.assertEqual(0, result.returncode, result.stderr)
        # A later completion reuses the existing plan record without prompting.
        complete = self.manifest("complete", SHA_B)
        source = self.board.root / "plan-owner.txt"
        original_source = source.read_bytes()
        source.write_text("revoked source")
        self.refused(lambda: self.accept("complete", SHA_B, complete), "checkpoint")
        source.write_bytes(original_source)
        original_decision = approval.read_bytes()
        approval.write_bytes(original_decision + b" ")
        self.refused(lambda: self.accept("complete", SHA_B, complete), "checkpoint")
        approval.write_bytes(original_decision)
        result = self.accept("complete", SHA_B, complete)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_plan_checkpoint_blocks_dispatch_until_scope_approval_exists(self):
        self.board.write_story(1, status="backlog", plan_checkpoint=True)
        self.refused(lambda: self.raw("orchestrator", "ready-for-dev"), "checkpoint")
        approval = self.approval("plan")
        result = self.raw("orchestrator", "ready-for-dev", "--decision", approval.name)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_configured_check_list_and_named_review_kind_are_preserved(self):
        (self.board.root / ".software-factory/config.yaml").write_text(json.dumps({
            "verification": {"required_checks": ["unit", "quality", "independent"]},
        }))
        path = self.manifest()
        report = json.loads(path.read_text())
        report["checks"] = {name: {**report["checks"]["tests"]} for name in ("unit", "quality", "independent")}
        report["checks"]["independent"]["kind"] = "review"
        self.write(path, report)
        result = self.accept(path=path)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_done_checkpoint_and_hitl_need_scoped_source_evidence(self):
        self.board.write_story(1, done_checkpoint=True, hitl=True)
        self.assertEqual(0, self.accept().returncode)
        path = self.manifest("complete", SHA_B)
        self.refused(lambda: self.accept("complete", SHA_B, path), "checkpoint")
        approval = self.approval("complete", scope=False, sha=SHA_B)
        decision = json.loads(approval.read_text())
        decision["scope"] = {"story": 2}
        self.write(approval, decision)
        self.refused(lambda: self.accept("complete", SHA_B, path, "--decision", approval.name))
        approval = self.approval("complete", scope=False, sha=SHA_B)
        source = self.board.root / "complete-owner.txt"
        source.write_text("modified source")
        self.refused(lambda: self.accept("complete", SHA_B, path, "--decision", approval.name))
        approval = self.approval("complete", scope=False, sha=SHA_B)
        result = self.accept("complete", SHA_B, path, "--decision", approval.name)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_revision_needs_live_ownership_and_preserves_previous_evidence(self):
        self.assertEqual(0, self.accept().returncode)
        accepted = self.board.story(1)["accepted_gates"]
        self.refused(lambda: self.raw("worker", "in-progress", "--owner", "other"))
        result = self.raw("worker", "in-progress", "--owner", "worker")
        self.assertEqual(0, result.returncode, result.stderr)
        story = self.board.story(1)
        self.assertEqual(accepted, story["gate_history"][0])
        self.assertNotIn("accepted_gates", story)
        self.assertIn("tests", story["receipts"])
        receipt = self.board.receipt("revision.json", sha=SHA_C)
        result = self.raw("worker", "in-review", "--owner", "worker", "--sha", SHA_C,
                          "--receipt", f"revision={receipt}")
        self.assertEqual(0, result.returncode, result.stderr)
        self.refused(lambda: self.accept(path=self.manifest()), "current review")
        revised = self.manifest(sha=SHA_C)
        result = self.accept(sha=SHA_C, path=revised)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_historical_done_record_stays_readable_and_frozen_without_gate_backfill(self):
        self.board.write_story(1, status="done", merged_sha="legacy-short")
        before = self.board.story_file(1).read_bytes()
        self.assertEqual(0, self.board.build().returncode)
        self.refused(lambda: self.raw("orchestrator", "built"), "frozen")
        self.assertEqual(before, self.board.story_file(1).read_bytes())

    def prepare_epic(self):
        self.assertEqual(0, self.accept().returncode)
        self.assertEqual(0, self.accept("complete", SHA_B).returncode)
        self.board.ws.run_state("release", "--task", "1", "--owner", "worker")
        self.board.make_ready(2, "worker-2", "src/gate.py")
        self.board.finish(2, "worker-2", SHA_C)
        result = self.board.epic(1, "--actor", "orchestrator", "--status", "awaiting-acceptance")
        self.assertEqual(0, result.returncode, result.stderr)
        return self.board.root / self.board.epic_approval(1)

    def close_epic(self, approval=None):
        args = ("--decision", approval.name) if approval else ()
        return self.board.board("epic", "--epic", "1", "--actor", "human", "--status", "done", *args)

    def test_epic_acceptance_needs_owner_source_and_independent_exact_scope_bundle(self):
        approval = self.prepare_epic()
        self.refused(lambda: self.close_epic(), "epic acceptance")
        source = self.board.root / "epic-1-owner.txt"
        original = source.read_bytes()
        source.write_text("source revoked")
        self.refused(lambda: self.close_epic(approval))
        source.write_bytes(original)
        bundle = self.board.root / "epic-1-review.json"
        original_bundle = bundle.read_bytes()
        report = json.loads(original_bundle)
        report["reviewer"] = report["author"]
        self.write(bundle, report)
        decision = json.loads(approval.read_text())
        decision["evidence"]["sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.write(approval, decision)
        self.refused(lambda: self.close_epic(approval))
        approval = self.board.root / self.board.epic_approval(1)
        report = json.loads(bundle.read_text())
        report["reviewer"] = "worker"
        self.write(bundle, report)
        decision = json.loads(approval.read_text())
        decision["evidence"]["sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.write(approval, decision)
        self.refused(lambda: self.close_epic(approval), "owns child implementation")
        approval = self.board.root / self.board.epic_approval(1)
        result = self.close_epic(approval)
        self.assertEqual(0, result.returncode, result.stderr)
        accepted = self.board.epic_record(1)
        self.assertTrue(accepted["acceptance"]["provenance_only"])
        self.assertEqual("human", accepted["acceptance"]["by"])
        self.assertEqual("fixture-owner", accepted["acceptance"]["approved_by"])
        self.assertEqual("done", accepted["status"])
        before = self.board.board_snapshot()
        result = self.close_epic(approval)
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, self.board.board_snapshot())

    def test_derive_cannot_rewrite_accepted_epic_scope_or_add_descendants(self):
        self.prepare_epic()
        # Exact scope binds these valid historical bytes, not a canonical rewrite.
        for story in (1, 2):
            self.board.story_file(story).write_text(json.dumps(self.board.story(story), separators=(",", ":")))
        approval = self.board.root / self.board.epic_approval(1)
        result = self.close_epic(approval)
        self.assertEqual(0, result.returncode, result.stderr)
        terminal_sources = {path: path.read_bytes() for path in
                            (self.board.epic_file(1), self.board.story_file(1), self.board.story_file(2))}
        result = self.board.derive_raw()
        self.assertEqual(0, result.returncode, result.stderr)
        for path, content in terminal_sources.items():
            self.assertEqual(content, path.read_bytes(), "idempotent derive changed terminal source")
        mutations = [
            lambda epic: epic.update(title="New title"),
            lambda epic: epic.update(outcome="New outcome"),
            lambda epic: epic.update(done_when=["New criterion"]),
            lambda epic: epic.update(covers=["New requirement"]),
            lambda epic: epic.update(needs=["ui"]),
            lambda epic: epic["stories"].reverse(),
            lambda epic: epic["stories"].append({"key": "new", "title": "New child"}),
            lambda epic: epic.update(stream="W-app"),
        ]
        for mutate in mutations:
            source = planning_source()
            mutate(source["epics"][0])
            with self.subTest(source=source):
                self.refused(lambda source=source: self.board.derive_raw(source), "frozen terminal")

    def test_stale_awaiting_acceptance_cannot_hide_a_new_open_descendant(self):
        approval = self.prepare_epic()
        child = roadmap.new_story(99, 1, "kernel", {"key": "new", "title": "New descendant"})
        self.write(self.board.story_file(99), child)
        epic = self.board.epic_record(1)
        epic["order"].append(99)
        self.write(self.board.epic_file(1), epic)
        self.refused(lambda: self.close_epic(approval), "open descendants")

    def test_legacy_child_requires_explicit_independent_reconciliation_not_backfill(self):
        self.prepare_epic()
        child_path = self.board.story_file(1)
        legacy = self.board.story(1)
        legacy.pop("accepted_gates")
        legacy.pop("evidence_contract")
        self.write(child_path, legacy)
        original = child_path.read_bytes()
        approval = self.board.root / self.board.epic_approval(1)
        decision = json.loads(approval.read_text())
        self.assertEqual([1], decision["legacy_children"])
        valid = approval.read_bytes()
        decision.pop("evidence")
        self.write(approval, decision)
        self.refused(lambda: self.close_epic(approval))
        approval.write_bytes(valid)
        result = self.close_epic(approval)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, child_path.read_bytes(), "legacy source was backfilled")

    def test_epic_bundle_needs_substantive_reconciliation_or_bound_outcome_bytes(self):
        self.prepare_epic()
        approval = self.board.root / self.board.epic_approval(1)
        bundle = self.board.root / "epic-1-review.json"
        report = json.loads(bundle.read_text())
        report.pop("reconciliation")
        self.write(bundle, report)
        decision = json.loads(approval.read_text())
        decision["evidence"]["sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.write(approval, decision)
        self.refused(lambda: self.close_epic(approval), "reconciliation detail")
        outcome = self.board.root / "outcome.txt"
        outcome.write_text("Synthetic independent outcome reconciliation fixture.")
        report["artifacts"] = [{"artifact": outcome.name,
                                "sha256": hashlib.sha256(outcome.read_bytes()).hexdigest()}]
        self.write(bundle, report)
        decision["evidence"]["sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.write(approval, decision)
        result = self.close_epic(approval)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_epic_reconciliation_refuses_changed_protected_child_scope(self):
        self.prepare_epic()
        self.board.write_story(1, title="Changed historical outcome")
        approval = self.board.root / self.board.epic_approval(1)
        self.refused(lambda: self.close_epic(approval), "child scope changed")

    def test_epic_initial_target_read_rejects_fifo_without_writes(self):
        approval = self.prepare_epic()
        target = self.board.epic_file(1)
        saved = target.read_bytes()
        target.unlink()
        os.mkfifo(target)
        try:
            self.refused(lambda: support.run(
                "roadmap", "--workspace", self.board.root, "epic", "--epic", "1",
                "--actor", "human", "--status", "done", "--decision", approval.name, timeout=3))
        finally:
            target.unlink()
            target.write_bytes(saved)

    def test_new_protected_child_cannot_take_the_legacy_reconciliation_path(self):
        self.prepare_epic()
        child = self.board.story(1)
        child.pop("accepted_gates")
        self.write(self.board.story_file(1), child)
        approval = self.board.root / self.board.epic_approval(1)
        self.refused(lambda: self.close_epic(approval), "cannot be accepted as legacy")



class RiskAdaptiveTests(unittest.TestCase):
    setUp = BoardGateTests.setUp
    raw = BoardGateTests.raw
    manifest = BoardGateTests.manifest
    write = BoardGateTests.write
    accept = BoardGateTests.accept
    refused = BoardGateTests.refused
    prepare_epic = BoardGateTests.prepare_epic

    def binding(self, name):
        return {"artifact": name, "sha256": hashlib.sha256((self.board.root / name).read_bytes()).hexdigest()}

    def prepare(self):
        self.prepare_epic()
        (self.board.root / "risk.md").write_text("Synthetic bounded local work; external effects reserved.")
        (self.board.root / "owner.txt").write_text("Synthetic scoped delegation, not authenticated owner authority.")
        grant = {"schema": "sf-epic-delegation/1", "decision": "delegate", "actions": ["accept-epic"],
                 "scope": {"epics": [1]}, "approved_by": "fixture-owner", "approved_at": "2020-01-01T00:00:00Z",
                 "source": {"kind": "user-conversation", "ref": "fixture:owner", **self.binding("owner.txt")}}
        self.write(self.board.root / "grant.json", grant)
        self.config = {"autonomy": {"mode": "risk-adaptive", "standing_delegations": []},
                       "checkpoints": {"manual": False, "transitions": ["epic-acceptance"]},
                       "documents": {"principles": {"risk": "risk.md"}}}
        self.refresh()

    def refresh(self):
        grant = self.binding("grant.json")
        self.config["autonomy"]["standing_delegations"] = [
            {"source": "grant.json", "sha256": grant["sha256"], "scope": "Accept finite epic 1"}]
        self.write(self.board.root / ".software-factory/config.yaml", self.config)
        # Reconcile exact scope after legitimate fixture changes, without approving them.
        self.board.epic_approval(1)
        scoped, _, _ = roadmap.epic_review_scope(self.board.root, roadmap.board_config(self.board.root), self.board.epic_record(1))
        assessment = {"schema": "sf-consequence-assessment/1", "scope": {"epic": 1}, "scope_sha256": scoped,
                      "config_sha256": self.binding(".software-factory/config.yaml")["sha256"],
                      "risk": self.binding("risk.md"), "delegation": grant, "evidence": self.binding("epic-1-review.json"),
                      "decision": "proceed", "reservations": [], "unknowns": [], "blocked_dependents": [],
                      "permission_status": "authorized", "effect_status": "pass", "recovery_status": "bounded", "risk_status": "resolved"}
        assessment.update({key: "Synthetic bounded local fixture with independent proof." for key in
                           ("cause", "outcome", "affected", "method", "permissions", "effect", "recovery", "blast_radius", "authority", "rationale")})
        review = json.loads((self.board.root / "epic-1-review.json").read_text())
        review["assessment_sha256"] = roadmap.gate_module().consequence_digest(assessment)
        self.write(self.board.root / "epic-1-review.json", review)
        assessment["evidence"] = self.binding("epic-1-review.json")
        self.write(self.board.root / "assessment.json", assessment)

    def close(self, *extra):
        return self.board.board("epic", "--epic", "1", "--actor", "orchestrator", "--status", "done",
                                "--owner", "acceptance-owner", "--delegation", "grant.json",
                                "--assessment", "assessment.json", "--evidence", "epic-1-review.json", *extra)

    def mutate(self, name, change):
        path = self.board.root / name
        record = json.loads(path.read_text())
        change(record)
        self.write(path, record)

    def test_complete_delegation_records_actual_actor_and_unlocks_epic(self):
        self.prepare()
        result = self.close()
        self.assertEqual(0, result.returncode, result.stderr)
        epic = self.board.epic_record(1)
        accepted = epic["acceptance"]
        self.assertEqual(("orchestrator", "delegated", "acceptance-owner"),
                         (accepted["by"], accepted["mode"], accepted["actor"]))
        self.assertEqual("orchestrator", epic["history"][-1]["by"])
        self.assertNotIn("decision", accepted)
        self.assertEqual(self.binding("grant.json"), accepted["delegation"])
        self.assertEqual("done", epic["status"])
        self.refused(self.close, "frozen")

    def test_supervised_legacy_manual_and_epic_reservations_refuse(self):
        self.prepare()
        for mode, manual in ((None, False), ("supervised", False), ("risk-adaptive", True), ("risk-adaptive", 0)):
            with self.subTest(mode=mode, manual=manual):
                self.config["autonomy"]["mode"] = mode
                self.config["checkpoints"]["manual"] = manual
                self.refresh()
                self.refused(self.close, "reserved")
        self.config["autonomy"]["mode"] = "risk-adaptive"
        self.config["checkpoints"]["manual"] = False
        self.mutate(self.board.epic_file(1).relative_to(self.board.root), lambda r: r.update(hitl=True))
        self.refresh()
        self.refused(self.close, "reserved")
        # Identical protected child/review proof remains usable by the actual human route.
        decision = self.board.epic_approval(1)
        result = self.board.board("epic", "--epic", "1", "--actor", "human", "--status", "done", "--decision", decision)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_revoked_expired_and_out_of_scope_grants_refuse(self):
        self.prepare()
        original = (self.board.root / "grant.json").read_bytes()
        changes = [lambda r: r.update(until="2020-01-02T00:00:00Z"),
                   lambda r: r.update(approved_at="2999-01-01T00:00:00Z"),
                   lambda r: r.update(approved_at="2020-01-01"),
                   lambda r: r.update(scope={"epics": [2]}), lambda r: r.update(scope={"epics": [True]}),
                   lambda r: r.update(scope={"epics": [1, 1]}), lambda r: r.update(scope={"epics": ["*"]}),
                   lambda r: r.update(scope={"epics": list(range(1, 258))}),
                   lambda r: r.update(actions=["accept-epic", "deploy"]), lambda r: r.update(reservation="ask first"),
                   lambda r: r["source"].update(kind="agent-summary")]
        for change in changes:
            (self.board.root / "grant.json").write_bytes(original)
            self.mutate("grant.json", change)
            self.refresh()
            self.refused(self.close)
        (self.board.root / "grant.json").write_bytes(original)
        self.refresh()
        self.config["autonomy"]["standing_delegations"] = []
        self.write(self.board.root / ".software-factory/config.yaml", self.config)
        self.refused(self.close)
        self.refresh()
        self.mutate("grant.json", lambda r: r.update(approved_by="changed-owner"))
        self.refused(self.close)
        self.refresh()
        (self.board.root / "owner.txt").write_text("replaced owner source")
        self.refused(self.close)

    def test_stale_policy_risk_scope_and_unknown_consequences_refuse(self):
        self.prepare()
        for name in ("risk.md", ".software-factory/config.yaml", "epic-1-review.json", "assessment.json"):
            path = self.board.root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            # Assessment bytes themselves need no prior approval; change a required fact instead.
            if name == "assessment.json":
                self.mutate(name, lambda r: r.update(decision="escalate"))
            self.refused(self.close)
            path.write_bytes(original)
        self.board.write_story(1, title="Changed accepted subject")
        self.refused(self.close)

    def test_each_unknown_or_missing_fact_refuses_even_with_current_bindings(self):
        self.prepare()
        path = self.board.root / "assessment.json"
        original = path.read_bytes()
        changes = {"permission_status": "unknown", "effect_status": "fail", "recovery_status": "unbounded",
                   "risk_status": "unknown", "reservations": ["production"], "unknowns": ["authority"],
                   "blocked_dependents": [1], "method": "", "scope": {"epic": True}, "rationale": "x" * 4097}
        for key, value in changes.items():
            path.write_bytes(original)
            self.mutate("assessment.json", lambda r, k=key, v=value: r.update({k: v}))
            self.refused(self.close)
        path.write_bytes(original)
        self.mutate("assessment.json", lambda r: r.pop("cause"))
        self.refused(self.close)

    def test_no_self_acceptance_or_review_or_human_label_laundering(self):
        self.prepare()
        self.refused(lambda: self.close("--owner", "worker"), "owns child implementation")
        self.refused(lambda: self.close("--decision", "epic-1-approval.json"))
        self.mutate("epic-1-review.json", lambda r: r.update(reviewer="worker"))
        self.mutate("assessment.json", lambda r: r.update(evidence=self.binding("epic-1-review.json")))
        self.refused(self.close, "owns child implementation")

    def test_legacy_needs_explicit_grant_and_never_backfills_history(self):
        self.prepare()
        self.mutate(self.board.story_file(1).relative_to(self.board.root),
                    lambda r: (r.pop("accepted_gates"), r.pop("evidence_contract")))
        original = self.board.story_file(1).read_bytes()
        self.refresh()
        self.refused(self.close, "delegation")
        self.mutate("grant.json", lambda r: r.update(legacy_children=[1]))
        self.refresh()
        result = self.close()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, self.board.story_file(1).read_bytes())

    def test_new_protected_child_cannot_use_delegated_legacy_authority(self):
        self.prepare()
        self.mutate(self.board.story_file(1).relative_to(self.board.root), lambda r: r.pop("accepted_gates"))
        self.mutate("grant.json", lambda r: r.update(legacy_children=[1]))
        self.refresh()
        self.refused(self.close, "cannot be accepted as legacy")

    def test_protected_snapshot_catches_replaced_source_ancestor_and_new_child(self):
        self.prepare()
        gate = roadmap.gate_module()
        real_review = gate.review_bundle
        args = types.SimpleNamespace(command="epic", epic="1", actor="orchestrator", status="done",
                                     owner="acceptance-owner", decision=None, delegation="grant.json",
                                     assessment="assessment.json", evidence="epic-1-review.json")
        before = self.board.board_snapshot()
        def swap(*a, **kw):
            result = real_review(*a, **kw)
            source = self.board.root / "owner.txt"
            content = source.read_bytes()
            source.rename(self.board.root / "old-owner.txt")
            source.write_bytes(content)
            return result
        with (mock.patch.object(gate, "review_bundle", side_effect=swap),
              self.assertRaisesRegex(roadmap.BoardError, "source changed")):
            roadmap.epic_update(self.board.root, args)
        self.assertEqual(before, self.board.board_snapshot())
        # Same bytes through a replaced ancestor must fail, too.
        directory = self.board.root / "proof"
        def ancestor(*a, **kw):
            result = real_review(*a, **kw)
            directory.rename(self.board.root / "old-proof")
            directory.mkdir()
            for path in (self.board.root / "old-proof").iterdir():
                (directory / path.name).write_bytes(path.read_bytes())
            return result
        with (mock.patch.object(gate, "review_bundle", side_effect=ancestor),
              self.assertRaisesRegex(roadmap.BoardError, "source changed")):
            roadmap.epic_update(self.board.root, args)
        self.assertEqual(before, self.board.board_snapshot())

    def test_symlink_and_ambiguous_grant_inputs_are_zero_write_refusals(self):
        self.prepare()
        path = self.board.root / "grant.json"
        original = path.read_bytes()
        path.write_bytes(original[:-1] + b',"decision":"delegate"}')
        self.refused(self.close)
        path.write_bytes(original)
        path.rename(self.board.root / "real-grant.json")
        path.symlink_to(self.board.root / "real-grant.json")
        self.refused(self.close)

    def test_derive_preserves_epic_reservation_when_source_omits_it(self):
        self.board.derive()
        self.mutate(self.board.epic_file(1).relative_to(self.board.root), lambda r: r.update(hitl=True))
        self.board.derive()
        self.assertIs(True, self.board.epic_record(1)["hitl"])


    def test_independent_review_must_cover_actual_consequence_assertions(self):
        self.prepare()
        self.mutate("assessment.json", lambda r: r.update(method="Different actual operation"))
        self.refused(self.close, "current consequence assessment")

    def test_new_child_during_review_is_detected_before_acceptance_publication(self):
        self.prepare()
        gate = roadmap.gate_module()
        real_review = gate.review_bundle
        args = types.SimpleNamespace(command="epic", epic="1", actor="orchestrator", status="done",
                                     owner="acceptance-owner", decision=None, delegation="grant.json",
                                     assessment="assessment.json", evidence="epic-1-review.json")
        stable = {p: p.read_bytes() for p in (self.board.epic_file(1), self.board.roadmap_file(), self.board.dashboard_file())}
        def add_child(*a, **kw):
            result = real_review(*a, **kw)
            child = roadmap.new_story(99, 1, "kernel", {"key": "extra", "title": "Unreviewed descendant"})
            self.write(self.board.story_file(99), child)
            return result
        with (mock.patch.object(gate, "review_bundle", side_effect=add_child),
              self.assertRaisesRegex(roadmap.BoardError, "source changed")):
            roadmap.epic_update(self.board.root, args)
        for path, original in stable.items():
            self.assertEqual(original, path.read_bytes())

    def test_post_review_config_grant_risk_and_assessment_changes_refuse(self):
        self.prepare()
        gate = roadmap.gate_module()
        real_review = gate.review_bundle
        args = types.SimpleNamespace(command="epic", epic="1", actor="orchestrator", status="done",
                                     owner="acceptance-owner", decision=None, delegation="grant.json",
                                     assessment="assessment.json", evidence="epic-1-review.json")
        for name in (".software-factory/config.yaml", "grant.json", "risk.md", "assessment.json"):
            path = self.board.root / name
            original = path.read_bytes()
            before = self.board.board_snapshot()
            def mutate(*a, path=path, original=original, **kw):
                result = real_review(*a, **kw)
                path.write_bytes(original + b" ")
                return result
            with (mock.patch.object(gate, "review_bundle", side_effect=mutate),
                  self.assertRaisesRegex(roadmap.BoardError, "source changed")):
                roadmap.epic_update(self.board.root, args)
            self.assertEqual(before, self.board.board_snapshot())
            path.write_bytes(original)

    def test_child_effect_and_required_human_checkpoint_are_not_waived(self):
        self.prepare()
        child = self.board.story(1)
        manifest = child['accepted_gates']['complete']['path']
        path = self.board.root / manifest
        original = path.read_bytes()
        self.mutate(manifest, lambda r: r['checks']['deploy'].update(status='unknown'))
        self.refused(self.close)
        path.write_bytes(original)
        self.board.write_story(1, done_checkpoint=True)
        self.refresh()
        self.refused(self.close)

    def test_delegation_expiring_during_review_refuses_before_publication(self):
        self.prepare()
        self.mutate("grant.json", lambda r: r.update(until="2026-01-01T00:00:00Z"))
        self.refresh()
        gate = roadmap.gate_module()
        real_datetime = gate.datetime
        class Clock(real_datetime):
            calls = 0

            @classmethod
            def now(cls, tz=None):
                cls.calls += 1
                return real_datetime.fromisoformat("2025-01-01T00:00:00Z" if cls.calls == 1 else "2027-01-01T00:00:00Z")
        args = types.SimpleNamespace(command="epic", epic="1", actor="orchestrator", status="done",
                                     owner="acceptance-owner", decision=None, delegation="grant.json",
                                     assessment="assessment.json", evidence="epic-1-review.json")
        before = self.board.board_snapshot()
        with mock.patch.object(gate, "datetime", Clock), self.assertRaisesRegex(roadmap.BoardError, "expired"):
            roadmap.epic_update(self.board.root, args)
        self.assertEqual(before, self.board.board_snapshot())

    def test_human_route_also_rejects_configuration_appearing_during_review(self):
        approval = self.prepare_epic()
        configuration = self.board.root / ".software-factory/config.yaml"
        configuration.unlink(missing_ok=True)
        gate = roadmap.gate_module()
        real_review = gate.review_bundle
        args = types.SimpleNamespace(command="epic", epic="1", actor="human", status="done",
                                     decision=approval.name, evidence=None)
        before = self.board.board_snapshot()
        def add_config(*a, **kw):
            result = real_review(*a, **kw)
            self.write(configuration, {"verification": {"required_checks": ["new-check"]}})
            return result
        with (mock.patch.object(gate, "review_bundle", side_effect=add_config),
              self.assertRaisesRegex(roadmap.BoardError, "source changed")):
            roadmap.epic_update(self.board.root, args)
        self.assertEqual(before, self.board.board_snapshot())
