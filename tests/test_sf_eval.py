"""Eval runner tests: the stdlib-only sf-eval runner and its receipts.

Covers the VAL-EVAL runner/receipt surface: the deterministic ladder rungs
(state, command, http, golden) executed natively and offline, harness rungs
(browser, judge) shelled out only to a declared harness with a missing
harness reported ``unverified`` and never as a pass, cost-tiered case
selection, nondeterministic trial aggregation, per-run and per-case receipts
with a sha256 self-hash, gate-manifest citation verification, recorded
overrides, quarantine, and an unchanged evaluated fixture.
"""
from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import support

REPO = support.REPO
SF_EVAL = REPO / "skills" / "sf-eval" / "scripts" / "sf_eval.py"
EXAMPLE_PLAN = REPO / "skills" / "sf-eval" / "examples" / "eval.config.example.json"


def run_eval(*args, cwd=None, env=None, timeout=120):
    """Run the eval runner CLI exactly the way a validator would."""
    return subprocess.run(
        [sys.executable, str(SF_EVAL), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )


def load_runner():
    """Import the runner as a module for unit-level checks."""
    spec = importlib.util.spec_from_file_location("sf_eval_runner", SF_EVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt_digest(obj):
    """The documented self-hash rule, reimplemented from the receipts contract."""
    payload = {key: value for key, value in obj.items() if key != "self_sha256"}
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def base_plan(cases):
    """A minimal signed-off plan wrapping the given cases."""
    return {
        "version": 1,
        "receipts_dir": ".software-factory/runs",
        "user_signoff_required": True,
        "risk_tier": 1,
        "surfaces": [
            {
                "id": "backend",
                "kind": "http-api",
                "base_url_env": "FIXTURE_API_URL",
                "harness": {"type": "http"},
                "suites": ["smoke", "story", "regression"],
            },
            {
                "id": "frontend",
                "kind": "web-ui",
                "harness": {"type": "browser"},
                "suites": ["smoke", "story"],
            },
            {
                "id": "behavior",
                "kind": "agent-llm",
                "harness": {"type": "judge"},
                "suites": ["story"],
            },
        ],
        "cases": cases,
        "modes": {
            "quick": {
                "allow_grades": ["state", "command", "http", "browser", "golden"]
            },
            "epic": {},
            "premerge": {"nondeterministic_trials": 2, "consistency": "pass^k"},
            "canary": {},
        },
        "routing": {"retry_cap_per_case": 3},
        "signoff": {
            "status": "approved",
            "approved_by": "fixture-user",
            "approved_at": "2026-10-11T00:00:00Z",
            "plan_sha256": "0" * 64,
        },
    }


def command_case(cid, story="S-1", suite="story", kind="fail_to_pass",
                 run="exit 0", surface="backend", **extra):
    """A command-graded case with the required traceability fields."""
    case = {
        "id": cid,
        "story": story,
        "epic": extra.pop("epic", "E-1"),
        "suite": suite,
        "kind": kind,
        "criterion": f"fixture criterion for {cid}",
        "surface": surface,
        "tier": extra.pop("tier", ["quick", "epic", "premerge", "canary"]),
        "grade": {"type": "command", "run": run, "expect": extra.pop("expect", {"exit": 0})},
        "nondeterministic": extra.pop("nondeterministic", False),
    }
    case.update(extra)
    return case


class Project:
    """A temporary consumer project holding an eval plan and its runs."""

    def __init__(self, test, plan):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "repo"
        self.root.mkdir()
        (self.root / "evals").mkdir()
        self.plan_path = self.root / "evals" / "eval.config.json"
        self.plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self.runs = self.root / ".software-factory" / "runs"

    def run(self, *args, env=None):
        merged = dict(os.environ)
        if env:
            merged.update(env)
        return run_eval(
            "run", "--plan", self.plan_path, "--project-root", self.root,
            "--runs-dir", self.runs, *args, env=merged,
        )

    def receipts(self):
        return sorted(self.runs.glob("*/evals/receipt.json"))

    def last_receipt(self):
        path = self.receipts()[-1]
        return path, json.loads(path.read_text(encoding="utf-8"))

    def case_result(self, case_id):
        path = self.receipts()[-1].parent / "cases" / f"{case_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))


class RunnerSourceChecks(unittest.TestCase):
    def test_stdlib_only(self):
        self.assertEqual(support.non_stdlib_imports(SF_EVAL), [])

    def test_no_agent_cli_or_model_invocation(self):
        text = SF_EVAL.read_text(encoding="utf-8")
        for needle in ("claude", "cursor-agent", "codex", "anthropic", "openai"):
            self.assertNotIn(needle, text.lower(), needle)

    def test_no_install_or_socket_code(self):
        text = SF_EVAL.read_text(encoding="utf-8")
        for needle in ("pip install", "import socket", "import requests",
                       "urlopen(\"https://", "urlopen('https://"):
            self.assertNotIn(needle, text)


class StateGradeTests(unittest.TestCase):
    def test_state_pass_writes_green_receipt(self):
        project = Project(self, base_plan([
            {
                "id": "BE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the result file records the answer",
                "surface": "backend",
                "grade": {"type": "state", "path": "out/result.json",
                          "json": {"answer": 42}},
            },
        ]))
        (project.root / "out").mkdir()
        (project.root / "out" / "result.json").write_text('{"answer": 42}')
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        _, receipt = project.last_receipt()
        self.assertEqual(receipt["verdict"], "pass")
        self.assertEqual(receipt["cases"], {"BE-ONE-001": "pass"})
        case = project.case_result("BE-ONE-001")
        self.assertEqual(case["criterion"], "the result file records the answer")
        self.assertFalse(
            (project.receipts()[-1].parent / "artifacts").exists(),
            "artifacts are written for failures only",
        )

    def test_state_fail_records_expected_and_actual(self):
        project = Project(self, base_plan([
            {
                "id": "BE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the result file exists", "surface": "backend",
                "grade": {"type": "state", "path": "out/result.json"},
            },
        ]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        case = project.case_result("BE-ONE-001")
        self.assertEqual(case["status"], "fail")
        self.assertIn("exists", case["expected"])
        self.assertEqual(case["actual"], "missing")
        self.assertEqual(case["triage_hint"]["route"], "code-fix")
        self.assertFalse(case["triage_hint"]["suspect_eval"])


class CommandGradeTests(unittest.TestCase):
    def test_command_exit_and_output_pattern(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="echo hello-factory",
                         expect={"exit": 0, "output_matches": "hello-factory"}),
        ]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_command_failure_captures_output_tail_artifact(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="echo oops-fixture && exit 3"),
        ]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        case = project.case_result("BE-ONE-001")
        self.assertEqual(case["status"], "fail")
        self.assertIn("exit 0", case["expected"])
        self.assertIn("exit 3", case["actual"])
        artifacts = case["artifacts"]
        self.assertEqual(len(artifacts), 1)
        tail = (project.receipts()[-1].parent / artifacts[0]).read_text()
        self.assertIn("oops-fixture", tail)


class GoldenGradeTests(unittest.TestCase):
    def make_project(self, golden_text, command):
        project = Project(self, base_plan([
            {
                "id": "BE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the generator output matches the approved golden",
                "surface": "backend",
                "grade": {"type": "golden", "golden": "evals/goldens/out.txt",
                          "command": command},
            },
        ]))
        (project.root / "evals" / "goldens").mkdir()
        (project.root / "evals" / "goldens" / "out.txt").write_text(golden_text)
        return project

    def test_golden_match_passes(self):
        project = self.make_project("approved-fixture\n", "echo approved-fixture")
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_golden_mismatch_writes_diff_artifact(self):
        project = self.make_project("approved-fixture\n", "echo actual-fixture")
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        case = project.case_result("BE-ONE-001")
        diff = (project.receipts()[-1].parent / case["artifacts"][0]).read_text()
        self.assertIn("-approved-fixture", diff)
        self.assertIn("+actual-fixture", diff)

    def test_missing_golden_is_unverified_never_a_pass(self):
        project = Project(self, base_plan([
            {
                "id": "BE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the golden exists", "surface": "backend",
                "grade": {"type": "golden", "golden": "evals/goldens/out.txt",
                          "command": "echo hi"},
            },
        ]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        _, receipt = project.last_receipt()
        self.assertEqual(receipt["verdict"], "unverified")
        self.assertEqual(project.case_result("BE-ONE-001")["status"], "unverified")


class HttpServerFixture(unittest.TestCase):
    """A loopback HTTP server on a kernel-assigned port, torn down per test."""

    def setUp(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/ok":
                    body = b'{"status": "ok", "count": 1}'
                    self.send_response(200)
                else:
                    body = b'{"error": "missing"}'
                    self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                """Silence the fixture server's request logging."""

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def http_case(self, expect, cid="BE-ONE-001"):
        return {
            "id": cid, "story": "S-1", "epic": "E-1", "suite": "story",
            "kind": "fail_to_pass",
            "criterion": "the endpoint answers with the fixture payload",
            "surface": "backend",
            "grade": {"type": "http", "request": {"path": "/ok"},
                      "expect": expect},
        }

    def test_http_status_and_json_assertions_pass(self):
        project = Project(self, base_plan([
            self.http_case({"status": 200, "json": {"status": "ok", "count": 1},
                            "contains": ["ok"]}),
        ]))
        result = project.run("--mode", "quick", "--story", "S-1",
                             env={"FIXTURE_API_URL": self.url})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_http_mismatch_fails_with_response_artifact(self):
        project = Project(self, base_plan([
            self.http_case({"status": 201}),
        ]))
        result = project.run("--mode", "quick", "--story", "S-1",
                             env={"FIXTURE_API_URL": self.url})
        self.assertEqual(result.returncode, 1)
        case = project.case_result("BE-ONE-001")
        self.assertEqual(case["status"], "fail")
        dump = (project.receipts()[-1].parent / case["artifacts"][0]).read_text()
        self.assertIn("200", dump)

    def test_missing_base_url_env_is_unverified(self):
        project = Project(self, base_plan([self.http_case({"status": 200})]))
        env = dict(os.environ)
        env.pop("FIXTURE_API_URL", None)
        result = run_eval(
            "run", "--plan", project.plan_path, "--project-root", project.root,
            "--runs-dir", project.runs, "--mode", "quick", "--story", "S-1",
            env=env,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(project.case_result("BE-ONE-001")["status"], "unverified")

    def test_non_local_url_is_refused_without_a_request(self):
        case = self.http_case({"status": 200})
        case["grade"]["request"] = {"url": "http://eval-fixture.invalid/ok"}
        project = Project(self, base_plan([case]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        case_result = project.case_result("BE-ONE-001")
        self.assertEqual(case_result["status"], "unverified")
        self.assertIn("non-local", case_result["detail"])


class HarnessGradeTests(unittest.TestCase):
    def write_harness(self, project, status="pass"):
        stub = project.root / "harness_stub.py"
        stub.write_text(
            "import json, sys\n"
            "case = json.loads(open(sys.argv[1]).read())\n"
            f"open(sys.argv[2], 'w').write(json.dumps({{'status': '{status}', "
            "'actual': 'stub observation'}))\n"
        )
        return stub

    def test_declared_harness_receives_case_and_writes_result(self):
        project = Project(self, base_plan([]))
        stub = self.write_harness(project)
        plan = base_plan([
            {
                "id": "FE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the page shows the confirmation text",
                "surface": "frontend",
                "grade": {"type": "browser", "steps": [{"goto": "/"}],
                          "expect": {"visible": "text=Done"}},
            },
        ])
        plan["surfaces"][1]["harness"]["run"] = f"{sys.executable} {stub}"
        project.plan_path.write_text(json.dumps(plan))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        case = project.case_result("FE-ONE-001")
        self.assertEqual(case["actual"], "stub observation")

    def test_missing_harness_is_unverified_never_a_pass(self):
        project = Project(self, base_plan([
            {
                "id": "BEH-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the copy is friendly", "surface": "behavior",
                "nondeterministic": True,
                "grade": {"type": "judge", "assertions": ["copy is friendly"],
                          "trials": 1, "consistency": "pass@k"},
            },
        ]))
        result = project.run("--mode", "epic", "--epic", "E-1")
        self.assertEqual(result.returncode, 1)
        case = project.case_result("BEH-ONE-001")
        self.assertEqual(case["status"], "unverified")
        self.assertIn("harness", case["detail"])

    def test_harness_not_found_is_unverified(self):
        project = Project(self, base_plan([]))
        plan = base_plan([
            {
                "id": "FE-ONE-001", "story": "S-1", "epic": "E-1",
                "suite": "story", "kind": "fail_to_pass",
                "criterion": "the page renders", "surface": "frontend",
                "grade": {"type": "browser"},
            },
        ])
        plan["surfaces"][1]["harness"]["run"] = "definitely-missing-sf-fixture-binary"
        project.plan_path.write_text(json.dumps(plan))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(project.case_result("FE-ONE-001")["status"], "unverified")


class ModeSelectionTests(unittest.TestCase):
    def build_project(self):
        cases = [
            command_case("FE-ONE-001", surface="frontend"),
            command_case("BE-ONE-001"),
            command_case("FE-ONE-002", surface="frontend", suite="smoke"),
            command_case("BE-ONE-002", kind="pass_to_pass"),
            command_case("BE-TWO-001", story="S-2", epic="E-2"),
            command_case("BE-TWO-002", story="S-2", epic="E-2", kind="pass_to_pass"),
            command_case("BE-DEPLOY-001", story="S-9", epic="E-3", suite="canary"),
            command_case("BEH-ONE-001", story="S-1", surface="behavior",
                         nondeterministic=True,
                         tier=["epic", "premerge"]),
        ]
        for case in cases:
            if case["id"] == "BEH-ONE-001":
                case["grade"] = {"type": "judge", "assertions": ["fixture"],
                                 "trials": 1, "consistency": "pass@k"}
        return Project(self, base_plan(cases))

    def selected(self, project):
        _, receipt = project.last_receipt()
        return set(receipt["cases"]), set(receipt["skipped"])

    def test_quick_runs_story_cases_plus_smoke_and_skips_the_judge(self):
        project = self.build_project()
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        ran, skipped = self.selected(project)
        self.assertEqual(
            ran, {"FE-ONE-001", "BE-ONE-001", "FE-ONE-002", "BE-ONE-002"}
        )
        self.assertEqual(skipped, {"BEH-ONE-001"})

    def test_epic_adds_the_full_regression_suite(self):
        project = self.build_project()
        result = project.run("--mode", "epic", "--epic", "E-1")
        self.assertEqual(result.returncode, 1)  # the harnessless judge is unverified
        ran, _ = self.selected(project)
        self.assertIn("BE-TWO-002", ran)  # regression from another epic
        self.assertNotIn("BE-TWO-001", ran)  # another epic's story case
        self.assertIn("BEH-ONE-001", ran)

    def test_premerge_runs_every_case(self):
        project = self.build_project()
        result = project.run("--mode", "premerge")
        self.assertEqual(result.returncode, 1)  # the harnessless judge is unverified
        ran, _ = self.selected(project)
        self.assertEqual(len(ran), 8)

    def test_canary_runs_smoke_and_canary_suites_only(self):
        project = self.build_project()
        result = project.run("--mode", "canary")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        ran, _ = self.selected(project)
        self.assertEqual(ran, {"FE-ONE-002", "BE-DEPLOY-001"})

    def test_quick_requires_a_story(self):
        project = self.build_project()
        result = project.run("--mode", "quick")
        self.assertEqual(result.returncode, 2)


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()

    def test_pass_at_k(self):
        aggregate = self.runner.aggregate_trials
        self.assertEqual(aggregate(["fail", "pass"], "pass@k"), "pass")
        self.assertEqual(aggregate(["fail", "fail"], "pass@k"), "fail")
        self.assertEqual(aggregate(["fail", "unverified"], "pass@k"), "unverified")

    def test_pass_caret_k(self):
        aggregate = self.runner.aggregate_trials
        self.assertEqual(aggregate(["pass", "pass"], "pass^k"), "pass")
        self.assertEqual(aggregate(["pass", "fail"], "pass^k"), "fail")

    def test_majority(self):
        aggregate = self.runner.aggregate_trials
        self.assertEqual(aggregate(["pass", "fail", "pass"], "majority"), "pass")
        self.assertEqual(aggregate(["pass", "fail", "fail"], "majority"), "fail")


class ReceiptTests(unittest.TestCase):
    def make_green(self):
        project = Project(self, base_plan([command_case("BE-ONE-001")]))
        result = project.run("--mode", "quick", "--story", "S-1")
        assert result.returncode == 0, result.stderr + result.stdout
        return project

    def test_receipt_fields_and_self_hash(self):
        project = self.make_green()
        _, receipt = project.last_receipt()
        for field in ("run_id", "mode", "story_ids", "started", "finished",
                      "git_sha", "config_sha256", "command", "cases", "totals",
                      "verdict", "overrides", "self_sha256"):
            self.assertIn(field, receipt, field)
        self.assertEqual(receipt["mode"], "quick")
        self.assertEqual(receipt["story_ids"], ["S-1"])
        self.assertEqual(receipt_digest(receipt), receipt["self_sha256"])

    def test_verify_receipt_accepts_green(self):
        project = self.make_green()
        path, _ = project.last_receipt()
        result = run_eval("verify", "--receipt", path)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_verify_receipt_detects_tampering(self):
        project = self.make_green()
        path, receipt = project.last_receipt()
        receipt["totals"]["passed"] = 99
        path.write_text(json.dumps(receipt, indent=2))
        result = run_eval("verify", "--receipt", path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("digest", result.stdout + result.stderr)

    def test_verify_receipt_rejects_a_failing_verdict(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="exit 1"),
        ]))
        project.run("--mode", "quick", "--story", "S-1")
        path, receipt = project.last_receipt()
        self.assertEqual(receipt["verdict"], "fail")
        result = run_eval("verify", "--receipt", path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("verdict", result.stdout + result.stderr)

    def test_receipts_are_text_and_sized(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="echo fixture-tail && exit 1"),
        ]))
        project.run("--mode", "quick", "--story", "S-1")
        evals_dir = project.receipts()[-1].parent
        for path in evals_dir.rglob("*"):
            if path.is_file():
                self.assertLess(path.stat().st_size, 64 * 1024, path)
                path.read_text(encoding="utf-8")  # text only, never binaries


class VerifyManifestTests(unittest.TestCase):
    def setUp(self):
        self.project = Project(self, base_plan([command_case("BE-ONE-001")]))
        result = self.project.run("--mode", "quick", "--story", "S-1")
        assert result.returncode == 0, result.stderr + result.stdout
        self.receipt_path, self.receipt = self.project.last_receipt()
        self.rel_receipt = self.receipt_path.relative_to(self.project.root)

    def manifest(self, block):
        path = self.project.root / "manifest.json"
        path.write_text(json.dumps({"subject_sha": "0" * 40, **block}))
        return path

    def good_block(self):
        return {
            "status": "pass",
            "run_id": self.receipt["run_id"],
            "verdict": "pass",
            "cases": self.receipt["cases"],
            "receipt": str(self.rel_receipt),
            "self_sha256": self.receipt["self_sha256"],
        }

    def verify(self, manifest_path):
        return run_eval("verify-manifest", "--manifest", manifest_path,
                        "--root", self.project.root)

    def test_citing_manifest_verifies(self):
        result = self.verify(self.manifest({"checks": {"eval": self.good_block()}}))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_top_level_eval_block_also_accepted(self):
        result = self.verify(self.manifest({"eval": self.good_block()}))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_missing_eval_block_is_refused(self):
        result = self.verify(self.manifest({"checks": {}}))
        self.assertEqual(result.returncode, 1)
        self.assertIn("eval block", result.stdout + result.stderr)

    def test_missing_receipt_is_refused(self):
        block = self.good_block()
        block["receipt"] = ".software-factory/runs/nope/evals/receipt.json"
        result = self.verify(self.manifest({"checks": {"eval": block}}))
        self.assertEqual(result.returncode, 1)
        self.assertIn("receipt", result.stdout + result.stderr)

    def test_altered_receipt_is_refused(self):
        manifest = self.manifest({"checks": {"eval": self.good_block()}})
        self.receipt["cases"]["BE-ONE-001"] = "fail"
        self.receipt_path.write_text(json.dumps(self.receipt, indent=2))
        result = self.verify(manifest)
        self.assertEqual(result.returncode, 1)
        self.assertIn("digest", result.stdout + result.stderr)

    def test_failing_receipt_verdict_is_refused(self):
        project = Project(self, base_plan([command_case("BE-ONE-001", run="exit 1")]))
        project.run("--mode", "quick", "--story", "S-1")
        path, receipt = project.last_receipt()
        block = {
            "status": "pass",
            "run_id": receipt["run_id"],
            "verdict": "fail",
            "cases": receipt["cases"],
            "receipt": str(path.relative_to(project.root)),
            "self_sha256": receipt["self_sha256"],
        }
        manifest = project.root / "manifest.json"
        manifest.write_text(json.dumps({"checks": {"eval": block}}))
        result = run_eval("verify-manifest", "--manifest", manifest,
                          "--root", project.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("verdict", result.stdout + result.stderr)

    def test_not_applicable_requires_an_override_record(self):
        block = {"status": "not_applicable"}
        result = self.verify(self.manifest({"checks": {"eval": block}}))
        self.assertEqual(result.returncode, 1)
        self.assertIn("override", result.stdout + result.stderr)
        block["override"] = {"who": "fixture-user",
                             "when": "2026-10-11T00:00:00Z",
                             "reason": "surface absent in this fixture"}
        result = self.verify(self.manifest({"checks": {"eval": block}}))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


class OverrideTests(unittest.TestCase):
    def test_override_is_recorded_and_rehashed(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="exit 1"),
        ]))
        project.run("--mode", "quick", "--story", "S-1")
        path, _ = project.last_receipt()
        result = run_eval("verify", "--receipt", path)
        self.assertEqual(result.returncode, 1)
        result = run_eval("override", "--receipt", path, "--who", "fixture-user",
                          "--reason", "accepted risk for the fixture demo")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = json.loads(path.read_text())
        self.assertEqual(len(receipt["overrides"]), 1)
        record = receipt["overrides"][0]
        self.assertEqual(record["who"], "fixture-user")
        self.assertEqual(record["reason"], "accepted risk for the fixture demo")
        self.assertTrue(record["when"])
        self.assertEqual(receipt_digest(receipt), receipt["self_sha256"])

    def test_override_requires_who_and_reason(self):
        project = Project(self, base_plan([command_case("BE-ONE-001")]))
        project.run("--mode", "quick", "--story", "S-1")
        path, _ = project.last_receipt()
        result = run_eval("override", "--receipt", path, "--who", "",
                          "--reason", "x")
        self.assertEqual(result.returncode, 2)


class QuarantineTests(unittest.TestCase):
    def test_quarantined_failure_does_not_block_the_verdict(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001"),
            command_case("BE-ONE-002", run="exit 1", quarantined=True),
        ]))
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        _, receipt = project.last_receipt()
        self.assertEqual(receipt["verdict"], "pass")
        self.assertEqual(receipt["totals"]["quarantined"], 1)
        self.assertEqual(receipt["cases"]["BE-ONE-002"], "fail")


class SuspectEvalTests(unittest.TestCase):
    def test_repeated_failures_flag_suspect_eval(self):
        project = Project(self, base_plan([
            command_case("BE-ONE-001", run="exit 1"),
        ]))
        for _ in range(3):
            project.run("--mode", "quick", "--story", "S-1")
        case = project.case_result("BE-ONE-001")
        self.assertFalse(case["triage_hint"]["suspect_eval"])
        project.run("--mode", "quick", "--story", "S-1")
        case = project.case_result("BE-ONE-001")
        self.assertTrue(case["triage_hint"]["suspect_eval"])
        self.assertEqual(case["triage_hint"]["route"], "eval-fix-review")


class FixtureUnchangedTests(unittest.TestCase):
    def test_run_leaves_the_fixture_tree_unchanged(self):
        project = Project(self, base_plan([command_case("BE-ONE-001")]))
        (project.root / ".gitignore").write_text(
            ".software-factory/runs/\n", encoding="utf-8"
        )
        git = support.Workspace.git
        git(project.root, "init", "-q", "-b", "main")
        git(project.root, "add", "-A")
        git(project.root, "-c", f"user.email={support.FIXTURE_EMAIL}",
            "-c", f"user.name={support.FIXTURE_NAME}",
            "commit", "-q", "-m", "fixture")
        result = project.run("--mode", "quick", "--story", "S-1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        status = git(project.root, "status", "--porcelain")
        self.assertEqual(status.stdout.strip(), "")
        _, receipt = project.last_receipt()
        self.assertRegex(receipt["git_sha"], r"^[0-9a-f]{40}$")


class PlanValidationTests(unittest.TestCase):
    def run_bad_plan(self, plan):
        project = Project(self, plan)
        return project.run("--mode", "quick", "--story", "S-1")

    def test_unknown_grade_type_fails_closed(self):
        case = command_case("BE-ONE-001")
        case["grade"] = {"type": "telepathy"}
        result = self.run_bad_plan(base_plan([case]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("telepathy", result.stderr)

    def test_duplicate_case_id_fails_closed(self):
        result = self.run_bad_plan(base_plan([
            command_case("BE-ONE-001"), command_case("BE-ONE-001"),
        ]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate", result.stderr)

    def test_judge_case_must_be_marked_nondeterministic(self):
        case = command_case("BEH-ONE-001", surface="behavior")
        case["grade"] = {"type": "judge", "assertions": ["x"]}
        result = self.run_bad_plan(base_plan([case]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("nondeterministic", result.stderr)

    def test_case_id_shape_is_enforced(self):
        case = command_case("be-one-1")
        result = self.run_bad_plan(base_plan([case]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("id", result.stderr.lower())


class ExamplePlanTests(unittest.TestCase):
    """The shipped worked example doubles as the contract's parse target."""

    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(EXAMPLE_PLAN.read_text(encoding="utf-8"))

    def test_ids_are_unique_stable_shaped_and_story_linked(self):
        ids = [case["id"] for case in self.plan["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.plan["cases"]:
            self.assertRegex(case["id"], r"^[A-Z][A-Z0-9]*-[A-Z0-9]+-[0-9]{3}$")
            self.assertTrue(case["story"], case["id"])
            self.assertTrue(case["criterion"], case["id"])
            self.assertIn(case["kind"], ("fail_to_pass", "pass_to_pass"))
            self.assertIn(
                case["grade"]["type"],
                ("state", "command", "http", "browser", "golden", "judge"),
            )

    def test_story_is_proven_on_two_surfaces(self):
        surfaces = {
            case["surface"]
            for case in self.plan["cases"]
            if case["story"] == "S-12"
        }
        self.assertIn("frontend", surfaces)
        self.assertIn("backend", surfaces)

    def test_judge_case_carries_every_constraint_marker(self):
        judges = [
            case for case in self.plan["cases"]
            if case["grade"]["type"] == "judge"
        ]
        self.assertTrue(judges, "the example needs a judge case")
        for case in judges:
            self.assertTrue(case["nondeterministic"], case["id"])
            grade = case["grade"]
            self.assertIsInstance(grade["assertions"], list)
            self.assertTrue(grade["reference_example"])
            self.assertEqual(grade["escape"], "Unknown")
            self.assertGreaterEqual(grade["trials"], 1)
            self.assertIn(grade["consistency"], ("pass@k", "pass^k", "majority"))

    def test_signoff_block_is_approved(self):
        signoff = self.plan["signoff"]
        self.assertEqual(signoff["status"], "approved")
        self.assertTrue(signoff["approved_by"])
        self.assertTrue(signoff["approved_at"])
        self.assertTrue(signoff["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
