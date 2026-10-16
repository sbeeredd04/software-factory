"""Tests for the evidence-gate kernel helper (gate.py).

Encodes the VAL-KERNEL gate assertions: subject SHA binding, reviewer
independence, phase-required checks, pass-status structure, strict integer
exit codes, artifact containment, deploy freshness, approved exceptions,
configuration-driven check names, and the never-execute rule.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

gate = support.helper("gate")
SCRIPTS = support.SCRIPTS
SHA = "a" * 40


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "evidence.txt").write_text("Synthetic fixture evidence\n")

    def report(self, phase="complete", **overrides):
        names = list(gate.DEFAULT_REQUIRED[phase])
        checks = {
            name: {
                "status": "pass",
                "subject_sha": SHA,
                "artifact": "evidence.txt",
                "exit_code": 0,
                "command": "fixture-command",
                "deployed_sha": SHA,
            }
            for name in names
        }
        report = {"subject_sha": SHA, "author": "author-a", "reviewer": "reviewer-b", "checks": checks}
        report.update(overrides)
        return report

    def write(self, report, name="report.json"):
        path = self.root / name
        path.write_text(json.dumps(report))
        return path

    def run_gate(self, report, phase="complete", sha=SHA, config=None):
        args = ["--report", self.write(report), "--root", self.root, "--sha", sha, "--phase", phase]
        if config is not None:
            args += ["--config", config]
        return support.run("gate", *args)


class StructureTests(GateFixture):
    def test_valid_complete_report_passes(self):
        result = self.run_gate(self.report())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Evidence structure complete", result.stdout)

    def test_valid_premerge_report_without_deploy_passes(self):
        result = self.run_gate(self.report(phase="premerge"), phase="premerge")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_required_checks_fail(self):
        report = self.report(phase="premerge")
        del report["checks"]["ci"]
        result = self.run_gate(report, phase="premerge")
        self.assertEqual(1, result.returncode)
        self.assertIn("ci: missing", result.stdout)
        report = self.report()
        del report["checks"]["deploy"]
        result = self.run_gate(report)
        self.assertEqual(1, result.returncode)
        self.assertIn("deploy: missing", result.stdout)

    def test_subject_sha_must_be_full_hex_and_match(self):
        report = self.report()
        result = self.run_gate(report, sha="abc123")
        self.assertEqual(1, result.returncode)
        self.assertIn("full Git SHA", result.stdout)
        result = self.run_gate(report, sha="A" * 40)
        self.assertEqual(1, result.returncode)
        report = self.report()
        report["subject_sha"] = "b" * 40
        result = self.run_gate(report)
        self.assertEqual(1, result.returncode)
        self.assertIn("does not match", result.stdout)

    def test_author_and_reviewer_must_differ_and_exist(self):
        for label, change in (
            ("same identity", {"reviewer": "author-a"}),
            ("no author", {"author": ""}),
            ("no reviewer", {"reviewer": None}),
        ):
            with self.subTest(case=label):
                report = self.report(**change)
                result = self.run_gate(report)
                self.assertEqual(1, result.returncode)
                self.assertIn("independent reviewer", result.stdout)

    def test_unsuccessful_statuses_never_pass_even_with_matching_sha(self):
        for status in ("fail", "skipped", "unknown", "infra_error", "not-started"):
            with self.subTest(status=status):
                report = self.report()
                report["checks"]["eval"]["status"] = status
                result = self.run_gate(report)
                self.assertEqual(1, result.returncode)
                self.assertIn("failed, incomplete or stale", result.stdout)

    def test_exit_code_must_be_integer_zero(self):
        for label, value in (
            ("boolean true", True),
            ("string zero", "0"),
            ("nonzero", 1),
            ("float zero", 0.0),
        ):
            with self.subTest(case=label):
                report = self.report()
                report["checks"]["tests"]["exit_code"] = value
                result = self.run_gate(report)
                self.assertEqual(1, result.returncode)
                self.assertIn("exit code not successful", result.stdout)
        report = self.report()
        del report["checks"]["tests"]["exit_code"]
        result = self.run_gate(report)
        self.assertEqual(1, result.returncode)
        self.assertIn("exit code not successful", result.stdout)
        report = self.report()
        del report["checks"]["review"]["command"]
        del report["checks"]["review"]["exit_code"]
        result = self.run_gate(report)
        self.assertEqual(0, result.returncode, result.stdout)

    def test_artifacts_must_be_relative_existing_files(self):
        for label, artifact in (
            ("absolute", "/etc/hostname"),
            ("escape", "../evidence.txt"),
            ("missing", "no-such-file.txt"),
        ):
            with self.subTest(case=label):
                report = self.report()
                report["checks"]["eval"]["artifact"] = artifact
                result = self.run_gate(report)
                self.assertEqual(1, result.returncode)
                self.assertIn("artifact", result.stdout)

    def test_deploy_sha_must_match_subject(self):
        report = self.report()
        report["checks"]["deploy"]["deployed_sha"] = "b" * 40
        result = self.run_gate(report)
        self.assertEqual(1, result.returncode)
        self.assertIn("deployed SHA mismatch", result.stdout)


class ExceptionTests(GateFixture):
    def test_not_applicable_requires_full_approval_record(self):
        base = {"status": "not_applicable", "reason": "documentation-only change"}
        for label, change in (
            ("stale subject", {"subject_sha": "b" * 40, "approved_by": "approver", "decision_ref": "D1"}),
            ("no approver", {"subject_sha": SHA, "approved_by": "", "decision_ref": "D1"}),
            ("no reason", {"subject_sha": SHA, "approved_by": "approver", "reason": "", "decision_ref": "D1"}),
            ("no decision ref", {"subject_sha": SHA, "approved_by": "approver"}),
        ):
            with self.subTest(case=label):
                report = self.report()
                report["checks"]["eval"] = {**base, **change}
                result = self.run_gate(report)
                self.assertEqual(1, result.returncode)
                self.assertIn("eval:", result.stdout)
        report = self.report()
        report["checks"]["eval"] = {
            **base,
            "subject_sha": SHA,
            "approved_by": "approver",
            "reason": "docs only",
            "decision_ref": "D1",
        }
        result = self.run_gate(report)
        self.assertEqual(0, result.returncode, result.stdout)


class ConfiguredChecksTests(GateFixture):
    def config_file(self, payload, name="config.yaml"):
        path = self.root / name
        path.write_text(json.dumps(payload))
        return path

    def test_required_checks_are_configuration_driven(self):
        config = self.config_file(
            {"verification": {"required_checks": ["tests", "eval", "review", "lint"]}}
        )
        checks = {
            name: {"status": "pass", "subject_sha": SHA, "artifact": "evidence.txt", "exit_code": 0}
            for name in ("tests", "eval", "review", "lint")
        }
        report = {"subject_sha": SHA, "author": "a", "reviewer": "b", "checks": checks}
        result = self.run_gate(report, phase="premerge", config=config)
        self.assertEqual(0, result.returncode, result.stdout)
        result = self.run_gate(report, phase="premerge")
        self.assertEqual(1, result.returncode)
        self.assertIn("ci: missing", result.stdout)
        del checks["lint"]
        result = self.run_gate(
            {"subject_sha": SHA, "author": "a", "reviewer": "b", "checks": checks},
            phase="premerge",
            config=config,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("lint: missing", result.stdout)

    def test_complete_phase_also_requires_deploy(self):
        config = self.config_file({"verification": {"required_checks": ["tests", "lint"]}})
        checks = {
            name: {"status": "pass", "subject_sha": SHA, "artifact": "evidence.txt", "exit_code": 0}
            for name in ("tests", "lint")
        }
        report = {"subject_sha": SHA, "author": "a", "reviewer": "b", "checks": checks}
        result = self.run_gate(report, phase="complete", config=config)
        self.assertEqual(1, result.returncode)
        self.assertIn("deploy: missing", result.stdout)
        checks["deploy"] = {"status": "pass", "subject_sha": SHA, "deployed_sha": SHA, "artifact": "evidence.txt"}
        result = self.run_gate(
            {"subject_sha": SHA, "author": "a", "reviewer": "b", "checks": checks},
            phase="complete",
            config=config,
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def test_unusable_config_fails_closed(self):
        broken = self.root / "broken-config.yaml"
        broken.write_text("verification: [")
        for label, config in (
            ("unreadable", self.root / "missing-config.yaml"),
            ("not JSON", broken),
            ("not an object", self.config_file(["list"])),
            ("no verification", self.config_file({"project": {}})),
            ("bad list", self.config_file({"verification": {"required_checks": "tests"}})),
        ):
            with self.subTest(case=label):
                result = self.run_gate(self.report(), config=config)
                self.assertEqual(1, result.returncode)
                self.assertIn("config", result.stdout)


class NoExecutionTests(GateFixture):
    def test_report_commands_are_never_executed(self):
        side_effect = self.root / "side-effect"
        report = self.report()
        for name in report["checks"]:
            report["checks"][name]["command"] = f"touch {side_effect}"
        result = self.run_gate(report)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertFalse(side_effect.exists())

    def test_source_has_no_execution_mechanism(self):
        source = (SCRIPTS / "gate.py").read_text()
        for banned in ("subprocess", "os.system", "popen", "eval(", "exec(", "system("):
            self.assertNotIn(banned, source)

    def test_imports_are_standard_library_only(self):
        self.assertEqual([], support.non_stdlib_imports(SCRIPTS / "gate.py"))


class BoundEvidenceTests(GateFixture):
    def bound_report(self):
        report = self.report("premerge")
        for check in report["checks"].values():
            check["artifact_sha256"] = gate.digest((self.root / "evidence.txt").read_bytes())
        return report

    def validate(self, report):
        return gate.validate_bound(report, self.root, SHA, "premerge",
                                   list(gate.DEFAULT_REQUIRED["premerge"]),
                                   scope={"story": 1}, scope_digest="b" * 64)

    def approval(self, phase):
        source = self.root / "owner.txt"
        source.write_text("Synthetic source evidence\n")
        record = {"decision": "approve", "scope": {"story": 1}, "phase": phase,
                  "subject_sha": SHA, "approved_by": "owner", "approved_at": "2026-10-15T00:00:00Z",
                  "source": {"kind": "approval-surface", "ref": "fixture:approval",
                             "artifact": source.name, "sha256": gate.digest(source.read_bytes())}}
        path = self.write(record, "decision.json")
        return path, gate.digest(path.read_bytes())

    def test_strict_digest_binding_does_not_change_legacy_gate_contract(self):
        self.assertEqual([], gate.validate(self.report("premerge"), self.root, SHA, "premerge"))
        self.assertTrue(self.validate(self.report("premerge")))
        self.assertEqual([], self.validate(self.bound_report()))

    def test_not_applicable_needs_bound_scoped_source_and_cannot_exclude_review(self):
        report = self.bound_report()
        path, digest = self.approval("exception:ci")
        report["checks"]["ci"] = {"status": "not_applicable", "subject_sha": SHA,
                                   "approved_by": "owner", "reason": "fixture-only exclusion",
                                   "decision_ref": path.name, "decision_sha256": digest}
        self.assertEqual([], self.validate(report))
        (self.root / "owner.txt").write_text("source changed")
        self.assertTrue(self.validate(report))
        path, digest = self.approval("exception:review")
        report["checks"]["review"] = {**report["checks"]["ci"], "decision_sha256": digest}
        self.assertTrue(self.validate(report))

    def test_contradictory_or_revoked_decision_is_refused(self):
        path, _ = self.approval("exception:ci")
        record = json.loads(path.read_text())
        for changes in ({"decision": "reject"}, {"phase": "other"},
                        {"subject_sha": "c" * 40, "scope_sha256": "b" * 64},
                        {"approved_at": "2026-10-15"}):
            path.write_text(json.dumps({**record, **changes}))
            with self.assertRaises((ValueError, TypeError)):
                gate.decision(self.root, path.name, gate.digest(path.read_bytes()),
                              scope={"story": 1}, phase="exception:ci", sha=SHA, scope_digest="b" * 64)

    def test_overridden_failure_needs_explicit_source_bound_disposition(self):
        receipt = {"subject_sha": SHA, "verdict": "pass",
                   "overrides": [{"from_verdict": "fail", "who": "owner", "when": "fixture", "reason": "fixture"}]}
        receipt["self_sha256"] = hashlib.sha256(json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()).hexdigest()
        path = self.write(receipt, "receipt.json")
        report = self.bound_report()
        report["checks"]["eval"].update(artifact=path.name, artifact_sha256=gate.digest(path.read_bytes()))
        self.assertTrue(self.validate(report))
        approval, digest = self.approval("override:eval")
        record = json.loads(approval.read_text())
        record["artifact_sha256"] = gate.digest(path.read_bytes())
        approval.write_text(json.dumps(record))
        digest = gate.digest(approval.read_bytes())
        report["checks"]["eval"].update(disposition="approved_override",
                                        override_decision_ref=approval.name, override_decision_sha256=digest)
        self.assertEqual([], self.validate(report))

    def test_bound_reads_refuse_parent_symlinks_and_non_regular_files(self):
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            gate.bound_read(self.root, "alias/evidence.txt")
        with self.assertRaises((OSError, ValueError)):
            gate.bound_read(self.root, ".")
        with self.assertRaises((OSError, ValueError)):
            gate.bound_names(self.root, "alias")
        (self.root / "records").mkdir()
        (self.root / "records/1.json").write_text("{}")
        (self.root / "records/2.json").write_text("{}")
        with self.assertRaises(ValueError):
            gate.bound_names(self.root, "records", limit=1)

    def test_strict_parser_rejects_duplicate_keys_and_non_finite_values(self):
        for text in ('{"decision":"revoke","decision":"approve"}',
                     '{"nested":{"verdict":"fail","verdict":"pass"}}',
                     '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}',
                     '{"value":1e999}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.strict_json(text)

    def test_required_check_count_and_aggregate_artifact_budget_are_finite(self):
        report = self.bound_report()
        errors = gate.validate_bound(report, self.root, SHA, "premerge",
                                     ["tests"] * (gate.MAX_REQUIRED_CHECKS + 1),
                                     scope={"story": 1}, scope_digest="b" * 64)
        self.assertIn("count", errors[0])
        artifact = self.root / "evidence.txt"
        artifact.write_bytes(b"a" * gate.MAX_EVIDENCE_BYTES)
        report = self.bound_report()
        names = ["review", *[f"check-{index}" for index in range(8)]]
        report["checks"] = {name: report["checks"]["tests"] for name in names}
        errors = gate.validate_bound(report, self.root, SHA, "premerge", names,
                                     scope={"story": 1}, scope_digest="b" * 64)
        self.assertIn("aggregate", errors[0])


if __name__ == "__main__":
    unittest.main()
