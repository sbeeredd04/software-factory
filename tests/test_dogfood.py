"""Dogfood checks: the pack runs on its own method (VAL-EVAL-010).

The committed ``.software-factory/context/`` home (principles modules,
CODEBASE.md, the board, the decision records) and the pack's own eval
suite (``evals/eval.config.json``) are load-bearing artifacts: these tests
prove they exist, stay fresh against their generators, run offline with no
model or agent CLI, and are wired into the gate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

REPO = support.REPO
CONTEXT = REPO / ".software-factory" / "context"
BOARD = CONTEXT / "board"
PLAN = REPO / "evals" / "eval.config.json"
RUNNER = REPO / "skills" / "sf-eval" / "scripts" / "sf_eval.py"
ROADMAP = REPO / "skills" / "software-factory" / "scripts" / "roadmap.py"
CRAWL = REPO / "skills" / "sf-crawl" / "scripts" / "crawl.py"
CHECK_ALL = REPO / "scripts" / "check_all.sh"
CONTRIBUTING = REPO / "CONTRIBUTING.md"
VOLATILE_ARTIFACT_LINES = ("- Source revision:", "- Generated:")
STATUS_RE = re.compile(r"^Status: (proposed|accepted|superseded-by-\d{4})\b", re.MULTILINE)
ADR_SECTIONS = (
    "## Context",
    "## Drivers",
    "## Options",
    "## Outcome",
    "## Consequences",
    "## Confirmation",
)


def load_sf_eval():
    """Load the eval runner module by file location."""
    spec = importlib.util.spec_from_file_location("sf_eval_dogfood", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(args, env=None, timeout=600):
    """Run a repo CLI exactly the way the gate would."""
    return subprocess.run(
        [sys.executable, *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
        timeout=timeout,
        check=False,
    )


def sha256_file(path):
    """Digest a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_digest(plan):
    """The sign-off digest: sha256 over the canonical plan minus `signoff`."""
    payload = {key: value for key, value in plan.items() if key != "signoff"}
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ContextHomeTest(unittest.TestCase):
    """The committed context home: principles, crawl artifact, decisions."""

    def test_four_principles_modules_with_required_content(self):
        """All four modules exist and carry their contract content."""
        modules = {
            "product.md": ("outcome", "non-goal"),
            "conventions.md": ("smallest complete diff", "reuse"),
            "risk.md": ("escalat", "human", "production", "publish"),
            "evals.md": ("eval-first", "deterministic"),
        }
        for name, needles in modules.items():
            path = CONTEXT / "principles" / name
            self.assertTrue(path.is_file(), f"missing {path}")
            text = path.read_text(encoding="utf-8").lower()
            for needle in needles:
                self.assertIn(needle, text, f"{name} is missing {needle!r}")

    def test_codebase_artifact_is_committed(self):
        """CODEBASE.md exists at the crawl's documented path."""
        artifact = CONTEXT / "CODEBASE.md"
        self.assertTrue(artifact.is_file())
        text = artifact.read_text(encoding="utf-8")
        self.assertIn("- Source revision:", text)

    def test_decision_records_follow_the_record_contract(self):
        """Every ADR: NNNN name, monotonic unique numbering, <=40 lines,
        ordered sections, and a lifecycle status line."""
        records = sorted((CONTEXT / "decisions").glob("*.md"))
        self.assertGreaterEqual(len(records), 17, "the generalized ADR set")
        numbers = []
        for record in records:
            number, separator, _slug = record.name.partition("-")
            self.assertTrue(separator, f"{record.name}: not NNNN-title form")
            self.assertRegex(number, r"^\d{4}$")
            numbers.append(int(number))
            text = record.read_text(encoding="utf-8")
            lines = text.splitlines()
            self.assertLessEqual(
                len(lines), 40, f"{record.name}: over the 40-line record bar"
            )
            positions = []
            for section in ADR_SECTIONS:
                self.assertIn(section, text, f"{record.name}: missing {section}")
                positions.append(text.index(section))
            self.assertEqual(
                positions, sorted(positions),
                f"{record.name}: sections out of order",
            )
            self.assertRegex(text, STATUS_RE)
        self.assertEqual(numbers, sorted(set(numbers)), "numbering not monotonic")

    def test_board_files_exist(self):
        """Records, the planning source and both projections are committed."""
        self.assertTrue((BOARD / "plan.json").is_file())
        self.assertTrue((BOARD / "streams.json").is_file())
        self.assertTrue((BOARD / "meta.json").is_file())
        epics = sorted((BOARD / "epics").glob("*.json"))
        stories = sorted((BOARD / "stories").glob("*.json"))
        self.assertGreaterEqual(len(epics), 5, "one epic per milestone")
        self.assertGreaterEqual(len(stories), 30, "one story per mission feature")
        self.assertTrue((BOARD / "roadmap.json").is_file())
        self.assertTrue((BOARD / "dashboard.html").is_file())


class ProjectionFreshnessTest(unittest.TestCase):
    """Committed projections regenerate byte-identically from live sources."""

    def test_roadmap_build_is_byte_identical(self):
        """`roadmap.py build` leaves both projections untouched."""
        targets = [BOARD / "roadmap.json", BOARD / "dashboard.html"]
        before = [sha256_file(path) for path in targets]
        result = run_cli([ROADMAP, "build", "--workspace", REPO])
        self.assertEqual(result.returncode, 0, result.stderr)
        after = [sha256_file(path) for path in targets]
        self.assertEqual(before, after, "committed projections are stale")

    def test_roadmap_reports_no_problems(self):
        """The board loads clean: no degenerate records, no dangling refs."""
        document = json.loads((BOARD / "roadmap.json").read_text(encoding="utf-8"))
        self.assertEqual(document["problems"], [])

    def test_codebase_regeneration_is_stable(self):
        """A fresh crawl differs from the artifact only in volatile lines."""
        with tempfile.TemporaryDirectory() as temp:
            fresh = Path(temp) / "CODEBASE.md"
            result = run_cli([CRAWL, REPO, "--artifact", fresh])
            self.assertEqual(result.returncode, 0, result.stderr)
            committed = (CONTEXT / "CODEBASE.md").read_text(encoding="utf-8")
            produced = fresh.read_text(encoding="utf-8")

        def stable(text):
            return [
                line for line in text.splitlines()
                if not line.startswith(VOLATILE_ARTIFACT_LINES)
            ]

        self.assertEqual(stable(committed), stable(produced))


class EvalPlanTest(unittest.TestCase):
    """The pack's own eval plan: signed off, traceable, covering."""

    def setUp(self):
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        self.cases = self.plan["cases"]

    def test_plan_loads_under_the_runner(self):
        """The runner's own structural validation accepts the plan."""
        load_sf_eval().load_plan(PLAN)

    def test_signoff_records_approval_and_digest(self):
        """The plan carries its own sign-off: who, when, and a real digest."""
        signoff = self.plan.get("signoff", {})
        self.assertEqual(signoff.get("status"), "approved")
        self.assertTrue(signoff.get("approved_by"))
        self.assertTrue(signoff.get("approved_at"))
        self.assertEqual(
            signoff.get("plan_sha256"), plan_digest(self.plan),
            "sign-off digest must reproduce over the plan minus `signoff`",
        )

    def test_cases_cover_kernel_helpers_and_tooling(self):
        """Minimum coverage: state/gate/hook/config plus every gate script."""
        commands = [case["grade"].get("run", "") for case in self.cases]
        for needle in (
            "test_state.py",
            "test_gate.py",
            "test_hook.py",
            "test_config_kernel.py",
            "scripts/validate.py",
            "scripts/scan_public.py",
            "scripts/check_links.py",
        ):
            self.assertTrue(
                any(needle in command for command in commands),
                f"no case runs {needle}",
            )
        wiring = [
            case for case in self.cases
            if case["grade"].get("path") == "scripts/check_all.sh"
        ]
        self.assertTrue(wiring, "no case checks the gate wiring")
        mermaid = [
            case for case in wiring
            if "check_mermaid" in "".join(case["grade"].get("contains", []))
        ]
        self.assertTrue(mermaid, "no case pins the Mermaid gate step")

    def test_case_fields_and_story_links(self):
        """Consumer case shape: kinds, tiers, and board-linked stories."""
        board_keys = set()
        for record in (BOARD / "stories").glob("*.json"):
            data = json.loads(record.read_text(encoding="utf-8"))
            board_keys.add(data.get("source_key"))
        for case in self.cases:
            self.assertIn(case["kind"], ("fail_to_pass", "pass_to_pass"))
            self.assertTrue(case.get("tier"), f"{case['id']}: no run tiers")
            self.assertIn(
                case["story"], board_keys,
                f"{case['id']}: story {case['story']!r} is not on the board",
            )

    def test_both_case_kinds_present(self):
        """The plan exercises fail_to_pass and pass_to_pass cases."""
        kinds = {case["kind"] for case in self.cases}
        self.assertEqual(kinds, {"fail_to_pass", "pass_to_pass"})


class EvalRunTest(unittest.TestCase):
    """The suite runs by one documented command, offline, and green."""

    def test_premerge_run_is_offline_green_and_guarded(self):
        """Full premerge run: verdict pass, receipt verifies, guard log empty."""
        env, log, _stub_dir = support.guard_env()
        env["SF_SKIP_NETWORK"] = "1"
        runs_dir = Path(tempfile.mkdtemp(prefix="sf-dogfood-runs-"))
        result = run_cli(
            [
                RUNNER, "run", "--plan", PLAN, "--mode", "premerge",
                "--project-root", REPO, "--runs-dir", runs_dir,
            ],
            env=env,
        )
        self.assertEqual(
            result.returncode, 0,
            f"eval run failed:\n{result.stdout}\n{result.stderr}",
        )
        receipts = sorted(runs_dir.glob("*/evals/receipt.json"))
        self.assertEqual(len(receipts), 1, "exactly one run receipt")
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["verdict"], "pass")
        module = load_sf_eval()
        self.assertEqual(module.receipt_digest(receipt), receipt["self_sha256"])
        verify = run_cli([RUNNER, "verify", "--receipt", receipts[0]], env=env)
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertFalse(
            log.exists() and log.read_text(encoding="utf-8").strip(),
            "a model or agent CLI was invoked during the eval run",
        )


class GateWiringTest(unittest.TestCase):
    """The pack's gate runs its own evals; the docs point at the artifacts."""

    def test_check_all_runs_the_pack_evals(self):
        """check_all.sh fails on a red eval verdict."""
        text = CHECK_ALL.read_text(encoding="utf-8")
        self.assertIn("sf_eval.py", text)
        self.assertIn("evals/eval.config.json", text)
        self.assertIn('run_step "evals', text)

    def test_contributing_names_the_dogfood_artifacts(self):
        """The contributor docs name the context home, board and eval plan."""
        text = CONTRIBUTING.read_text(encoding="utf-8")
        for needle in (
            ".software-factory/context/",
            "evals/eval.config.json",
            "dashboard.html",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
