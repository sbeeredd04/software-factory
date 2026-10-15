"""New protected transitions consume real gate validation, not status labels.

All effect/approval fixtures are synthetic structural evidence; no external
integration, authenticated authority or deployment is asserted by these tests.
"""
from __future__ import annotations

import hashlib
import json
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

    def test_protected_config_first_read_is_bounded_and_no_follow(self):
        config = self.board.root / ".software-factory/config.yaml"
        external = self.board.root / "external-config.json"
        external.write_text('{}')
        config.symlink_to(external)
        self.refused(lambda: self.accept(), "configuration")
        config.unlink()
        config.write_bytes(b" " * (1024 * 1024 + 1))
        self.refused(lambda: self.accept(), "configuration")
        config.write_text('{}')
        path = self.manifest()
        original = Path.read_text

        def guarded_read(path, *args, **kwargs):
            self.assertNotEqual(config, path, "protected config used the legacy unbounded reader")
            return original(path, *args, **kwargs)

        args = types.SimpleNamespace(command="update", actor="orchestrator", status="built", story=1,
                                     sha=SHA_A, evidence=path.relative_to(self.board.root).as_posix(),
                                     decision=None, receipt=None, finding=None, unblock=False, block=None)
        with mock.patch.object(Path, "read_text", new=guarded_read):
            record = roadmap.update_story(self.board.root, args)
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

    def test_new_protected_child_cannot_take_the_legacy_reconciliation_path(self):
        self.prepare_epic()
        child = self.board.story(1)
        child.pop("accepted_gates")
        self.write(self.board.story_file(1), child)
        approval = self.board.root / self.board.epic_approval(1)
        self.refused(lambda: self.close_epic(approval), "cannot be accepted as legacy")

