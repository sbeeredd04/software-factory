"""Documented consumer commands and bounded example contracts, without agent CLIs."""
from __future__ import annotations

import copy
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import support

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DOCS = ROOT / "docs"
PYTHON = sys.executable


def check_synthetic_fixture(scenario: dict, files: dict) -> None:
    """Reject four named teaching-data mistakes; this is not an operation engine."""
    if scenario.get("observation_scope") != "read bounded local fixture output during this session":
        raise ValueError("fixture observation scope changed")
    if scenario.get("repair_scope") != "separate reviewed feature or bug claim required":
        raise ValueError("observation does not grant repair")
    if scenario.get("rollback_scope") != "separate approved local restoration and proof required":
        raise ValueError("observation does not grant rollback")
    start, end = scenario["window"]["start"], scenario["window"]["end"]
    if scenario["window"]["maximum_records"] != 3:
        raise ValueError("fixture observation record bound changed")
    if any(not start <= item["observed_at"] <= end for item in files.values()):
        raise ValueError("observation outside authorized window")
    routes = scenario.get("open_event_routes", [])
    if routes != [
        {"event_id": scenario["same_open_event"], "issue": "bug/type", "action": "open"},
        {"event_id": scenario["same_open_event"], "issue": "bug/type", "action": "update-existing"},
    ]:
        raise ValueError("repeat of open signal must update the same issue")
    no_fix = files["no-fix"]
    if (no_fix.get("result") != "correct-behavior" or no_fix.get("product_diff_files") != 0
            or no_fix.get("disposition") != "no-fix investigative closure; no implementation or deploy receipt"
            or "delivery_receipt" in no_fix or "implementation" in no_fix):
        raise ValueError("no-fix cannot claim code delivery")


def literal_install_command(document: str, variables: dict[str, str]) -> list[str]:
    """Accept one documented install invocation, never a general shell program."""
    matches = [line for line in document.splitlines() if line.startswith('"$SF_PYTHON" -I -B "$SF_PACK/install.py" install ')]
    if not matches:
        raise ValueError("no literal install command")
    tokens = shlex.split(matches[0])
    known = {"$SF_PYTHON": variables["SF_PYTHON"], "$SF_PACK/install.py": variables["SF_PACK"] + "/install.py",
             "$SF_HOST": variables["SF_HOST"], "$SF_PROJECT": variables["SF_PROJECT"]}
    args = [known.get(token, token) for token in tokens]
    expected = [variables["SF_PYTHON"], "-I", "-B", variables["SF_PACK"] + "/install.py",
                "install", "--host", variables["SF_HOST"], "--project", variables["SF_PROJECT"],
                "--profile", "full", "--skip-bmad", "--dry-run"]
    if args != expected:
        raise ValueError("documented install flags differ from reviewed offline grammar")
    return args


class DocsJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sf-docs-journey-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.env, self.guard, stubs = support.guard_env()
        self.addCleanup(shutil.rmtree, stubs, ignore_errors=True)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def tearDown(self):
        self.assertFalse(self.guard.exists(), "forbidden host CLI invoked")

    def cli(self, *argv: object, cwd: Path | None = None, env: dict[str, str] | None = None):
        return subprocess.run([str(arg) for arg in argv], cwd=cwd or ROOT, env=env or self.env,
                              capture_output=True, text=True, timeout=90, check=False)

    def consumer(self, name: str = "minimal", suffix: str = "") -> Path:
        target = self.base / (name + suffix)
        shutil.copytree(EXAMPLES / name, target, ignore=shutil.ignore_patterns("__pycache__", "node_modules", "dist"))
        return target

    def test_manual_and_four_examples_have_substantive_entries(self):
        for name in ("quickstart", "installation", "configuration", "hosts", "agents", "team",
                     "bots", "bmad", "evolve", "verification", "security", "recovery",
                     "limitations", "smoke-test", "DOGFOOD"):
            content = (DOCS / (name + ".md")).read_text()
            self.assertGreater(len(content.split()), 80, name)
            self.assertNotIn("Private story31 preparation", content)
        for name in ("minimal", "python-api", "typescript-web", "synthetic-run"):
            content = (EXAMPLES / name / "README.md").read_text()
            self.assertGreater(len(content.split()), 70, name)
            for source in ("PRINCIPLES.md", "ARCHITECTURE.md", "CONVENTIONS.md", "RISK.md", "TASKS.md"):
                self.assertTrue((EXAMPLES / name / source).is_file(), (name, source))

    def test_literal_install_command_and_changed_flag_refusal(self):
        text = (DOCS / "quickstart.md").read_text()
        variables = {"SF_PYTHON": PYTHON, "SF_PACK": str(ROOT), "SF_HOST": "codex", "SF_PROJECT": str(self.base / "project")}
        args = literal_install_command(text, variables)
        self.assertEqual("--dry-run", args[-1])
        with self.assertRaises(ValueError):
            literal_install_command(text.replace("--skip-bmad --dry-run", "--allow-overwrite README.md --dry-run", 1), variables)

    def test_documented_helper_mapping_runs_on_three_hosts(self):
        quickstart = (DOCS / "quickstart.md").read_text()
        mapping = re.search(r'```sh\n(case "\$SF_HOST" in\n.*?SF_KERNEL="\$SF_SKILLS/software-factory/scripts")\n```',
                            quickstart, re.DOTALL)
        self.assertIsNotNone(mapping, "quickstart must define one literal host mapping")
        onboarding = (DOCS / "onboarding.md").read_text()
        discover = '"$SF_PYTHON" -I -B "$SF_SKILLS/sf-help/scripts/discover.py" --project "$SF_PROJECT" --json'
        self.assertIn(discover, onboarding)
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                project = self.consumer(suffix="-helper-" + host)
                install = self.cli(PYTHON, "-I", "-B", ROOT / "install.py", "install", "--host", host,
                                   "--project", project, "--profile", "full", "--skip-bmad")
                self.assertEqual(0, install.returncode, install.stderr[-1200:])
                env = dict(self.env, SF_PYTHON=PYTHON, SF_HOST=host, SF_PROJECT=str(project))
                command = mapping.group(1) + "\n" + discover + "\n"
                result = self.cli("/bin/sh", "-eu", "-c", command, env=env)
                self.assertEqual(0, result.returncode, result.stderr[-1200:])
                self.assertIn("capabilities", json.loads(result.stdout))

    def test_actual_release_manual_link_and_anchor_closure(self):
        output = self.base / "release"
        built = self.cli(PYTHON, "-B", ROOT / "scripts/build_release.py",
                         "--ref", "v0.1.0", "--out", output)
        self.assertEqual(0, built.returncode, built.stderr[-1200:])
        with tarfile.open(output / "sf-v0.1.0.tar.gz", "r:gz") as archive:
            files = {member.name.removeprefix("sf-v0.1.0/"): archive.extractfile(member).read()
                     for member in archive if member.isfile()}
        self.assertTrue("docs/README.md" in files)
        self.assertTrue("SECURITY.md" in files)
        self.assertFalse(".software-factory/context/decisions/0025-bmad-module-compatibility-pins.md" in files)
        for name, raw in files.items():
            if not name.endswith(".md") or name.startswith("dist/plugins/"):
                continue
            content = raw.decode("utf-8")
            for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', content):
                reference = match.group(1)
                if "://" in reference or reference.startswith("mailto:"):
                    continue
                target, _, anchor = reference.partition("#")
                path = posixpath.normpath(posixpath.join(posixpath.dirname(name), target or posixpath.basename(name)))
                self.assertTrue(path in files, f"released {name} links to absent {reference}")
                if anchor:
                    headings = re.findall(r'^#{1,6}\s+(.+?)\s*#*$', files[path].decode("utf-8"), re.MULTILINE)
                    slugs = {re.sub(r'[^\w -]', '', heading.replace('`', '').lower()).replace(' ', '-')
                             for heading in headings}
                    self.assertIn(anchor, slugs, f"released {name} links to absent anchor {reference}")

    def test_documented_full_install_preserves_bytes_on_three_hosts(self):
        document = (DOCS / "quickstart.md").read_text()
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                project = self.consumer(suffix="-" + host)
                sentinels = {name: (project / name).read_bytes() for name in ("README.md", "CONVENTIONS.md")}
                before = support.tree_hashes(project)
                args = literal_install_command(document, {"SF_PYTHON": PYTHON, "SF_PACK": str(ROOT),
                                                           "SF_HOST": host, "SF_PROJECT": str(project)})
                preview = self.cli(*args)
                self.assertEqual(0, preview.returncode, preview.stderr[-1200:])
                self.assertEqual(before, support.tree_hashes(project))
                first = self.cli(*args[:-1])
                self.assertEqual(0, first.returncode, first.stderr[-1200:])
                manifest = project / ".software-factory/installation.json"
                self.assertTrue(manifest.is_file())
                self.assertEqual([host], json.loads(manifest.read_text())["hosts"])
                after = support.tree_hashes(project)
                repeat = self.cli(*args[:-1])
                self.assertEqual(0, repeat.returncode, repeat.stderr[-1200:])
                self.assertEqual(after, support.tree_hashes(project))
                for name, content in sentinels.items():
                    self.assertEqual(content, (project / name).read_bytes())

    def test_skills_only_is_fresh_and_omits_full_runtime(self):
        project = self.consumer(suffix="-skills")
        result = self.cli(PYTHON, "-I", "-B", ROOT / "install.py", "install", "--host", "codex",
                          "--project", project, "--profile", "skills-only", "--skip-bmad")
        self.assertEqual(0, result.returncode, result.stderr[-1200:])
        self.assertTrue((project / ".agents/skills/software-factory/SKILL.md").is_file())
        self.assertFalse((project / ".codex/agents").exists())
        self.assertFalse((project / ".software-factory/runtime").exists())
        self.assertEqual("skills-only", json.loads((project / ".software-factory/installation.json").read_text())["profile"])

    def test_discover_crawl_propose_apply_and_reuse(self):
        project = self.consumer(suffix="-setup")
        before = (project / "CONVENTIONS.md").read_bytes()
        skills = ROOT / "skills"
        discover = self.cli(PYTHON, "-I", "-B", skills / "sf-help/scripts/discover.py", "--project", project, "--json")
        self.assertEqual(0, discover.returncode, discover.stderr[-1200:])
        self.assertEqual("unknown", json.loads(discover.stdout)["capabilities"]["auth"])
        crawl = self.cli(PYTHON, "-I", "-B", skills / "sf-crawl/scripts/crawl.py", project,
                         "--artifact", project / ".software-factory/context/CODEBASE.md", "--json", self.base / "crawl.json")
        self.assertEqual(0, crawl.returncode, crawl.stderr[-1200:])
        propose = self.cli(PYTHON, "-I", "-B", skills / "sf-help/scripts/setup.py", "propose", "--project", project)
        self.assertEqual(0, propose.returncode, propose.stderr[-1200:])
        proposal = json.loads(propose.stdout)
        self.assertEqual(20, len(proposal["answers"]))
        review = self.base / "proposal.json"
        review.write_text(propose.stdout)
        wrong = self.cli(PYTHON, "-I", "-B", skills / "sf-help/scripts/setup.py", "apply", "--project", project,
                         "--proposal", review, "--approve-sha", "0" * 64, "--decision-ref", "synthetic-fixture-decision")
        self.assertNotEqual(0, wrong.returncode)
        apply = self.cli(PYTHON, "-I", "-B", skills / "sf-help/scripts/setup.py", "apply", "--project", project,
                         "--proposal", review, "--approve-sha", proposal["sha256"], "--decision-ref", "synthetic-fixture-decision")
        self.assertEqual(0, apply.returncode, apply.stderr[-1200:])
        validate = self.cli(PYTHON, "-I", "-B", skills / "software-factory/scripts/config.py", "validate",
                            "--config", project / ".software-factory/config.yaml", "--root", project)
        self.assertEqual(0, validate.returncode, validate.stderr[-1200:])
        configured = json.loads((project / ".software-factory/config.yaml").read_text())
        self.assertEqual("bmad", configured["planning"]["method"])
        self.assertEqual("risk-adaptive", configured["autonomy"]["mode"])
        self.assertIs(configured["checkpoints"]["manual"], False)
        for key in ("local_edits", "commits"):
            self.assertIs(configured["autonomy"][key], True)
        for key in ("push", "open_pr", "merge_integration", "deploy"):
            self.assertIs(configured["autonomy"][key], False)
        self.assertEqual(before, (project / "CONVENTIONS.md").read_bytes())
        reused = self.cli(PYTHON, "-I", "-B", skills / "sf-help/scripts/setup.py", "propose", "--project", project)
        self.assertEqual("sf-setup-reuse/1", json.loads(reused.stdout)["schema"])

    def test_stale_setup_refuses_and_preserves_collision(self):
        project = self.consumer(suffix="-stale")
        crawl = self.cli(PYTHON, "-I", "-B", ROOT / "skills/sf-crawl/scripts/crawl.py", project,
                         "--artifact", project / ".software-factory/context/CODEBASE.md", "--json", self.base / "crawl2.json")
        self.assertEqual(0, crawl.returncode, crawl.stderr[-1200:])
        propose = self.cli(PYTHON, "-I", "-B", ROOT / "skills/sf-help/scripts/setup.py", "propose", "--project", project)
        self.assertEqual(0, propose.returncode, propose.stderr[-1200:])
        proposal = json.loads(propose.stdout)
        review = self.base / "stale.json"
        review.write_text(propose.stdout)
        target = project / ".software-factory/config.yaml"
        target.write_text("user-owned collision\n")
        saved = target.read_bytes()
        applied = self.cli(PYTHON, "-I", "-B", ROOT / "skills/sf-help/scripts/setup.py", "apply", "--project", project,
                           "--proposal", review, "--approve-sha", proposal["sha256"], "--decision-ref", "synthetic-fixture-decision")
        self.assertNotEqual(0, applied.returncode)
        self.assertEqual(saved, target.read_bytes())

    def test_read_only_agent_registry_and_uninstall_preview(self):
        project = self.consumer(suffix="-reads")
        installed = self.cli(PYTHON, "-I", "-B", ROOT / "install.py", "install", "--host", "codex",
                             "--project", project, "--profile", "full", "--skip-bmad")
        self.assertEqual(0, installed.returncode, installed.stderr[-1200:])
        before = support.tree_hashes(project)
        skills = project / ".agents/skills"
        unavailable = self.cli(PYTHON, "-I", "-B", skills / "sf-agents/scripts/agents.py",
                               "--project", project, "discover")
        self.assertEqual(1, unavailable.returncode)
        self.assertIn("configuration missing", unavailable.stderr)
        self.assertEqual(before, support.tree_hashes(project))
        for argv in ((skills / "sf-evolve/scripts/evolve.py", "registry", "--root", project),
                     (ROOT / "install.py", "uninstall", "--project", project, "--host", "codex", "--dry-run")):
            result = self.cli(PYTHON, "-I", "-B", *argv)
            self.assertEqual(0, result.returncode, result.stderr[-1200:])
            self.assertEqual(before, support.tree_hashes(project))

    def test_offline_doctor_uses_controlled_auth_stub(self):
        project = self.consumer(suffix="-doctor")
        installed = self.cli(PYTHON, "-I", "-B", ROOT / "install.py", "install", "--host", "codex",
                             "--project", project, "--profile", "full", "--skip-bmad")
        self.assertEqual(0, installed.returncode, installed.stderr[-1200:])
        stub = self.base / "offline-bin"
        stub.mkdir()
        log = self.base / "gh-args.txt"
        gh = stub / "gh"
        gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SF_GH_LOG"\nexit 1\n')
        gh.chmod(0o755)
        env = dict(self.env, PATH=str(stub) + os.pathsep + self.env["PATH"], SF_GH_LOG=str(log))
        before = support.tree_hashes(project)
        result = self.cli(PYTHON, "-I", "-B", ROOT / "install.py", "doctor", "--project", project, "--json", env=env)
        self.assertIn(result.returncode, (0, 1), result.stderr[-1200:])
        self.assertIn("auth status", log.read_text())
        self.assertEqual(before, support.tree_hashes(project))

    def test_python_examples_execute_contracts(self):
        for name, positive, negative in (("minimal", ["Ada"], []),
                                         ("python-api", ["--once", '{"name":"Ada"}'], ["--once", '{"name":null}'])):
            with self.subTest(name=name):
                project = self.consumer(name, "-behavior")
                suite = self.cli(PYTHON, "-B", "-m", "unittest", "discover", "-s", "tests", "-v", cwd=project)
                self.assertEqual(0, suite.returncode, suite.stderr[-1200:])
                entry = "greet.py" if name == "minimal" else "app.py"
                good = self.cli(PYTHON, "-B", entry, *positive, cwd=project)
                self.assertEqual(0, good.returncode, good.stderr[-1200:])
                self.assertIn("Ada", good.stdout)
                if negative:
                    bad = self.cli(PYTHON, "-B", entry, *negative, cwd=project)
                    self.assertEqual(2, bad.returncode)
                    self.assertIn("error", bad.stdout)

    def test_synthetic_authority_unknown_dedup_and_expiry(self):
        root = EXAMPLES / "synthetic-run"
        scenario = json.loads((root / "scenario.json").read_text())
        self.assertTrue(scenario["synthetic"])
        self.assertNotEqual(scenario["observation_scope"], scenario["repair_scope"])
        self.assertNotEqual(scenario["repair_scope"], scenario["rollback_scope"])
        self.assertEqual(3, scenario["window"]["maximum_records"])
        files = {path.stem: json.loads(path.read_text()) for path in (root / "evidence").glob("*.json")}
        operations = (ROOT / "skills/software-factory/references/operations.md").read_text()
        self.assertIn("Read access does not authorize repair", operations)
        self.assertIn("Repeated evidence updates the same open issue", operations)
        check_synthetic_fixture(scenario, files)
        self.assertEqual(11, len(files))
        self.assertTrue(all(value["synthetic"] and value["origin"] == "invented-teaching-data" for value in files.values()))
        self.assertEqual(files["bug-before"]["event_id"], files["bug-after"]["event_id"])
        self.assertEqual([], files["unknown"]["records"])
        self.assertEqual("unknown", files["unknown"]["result"])
        self.assertEqual(0, files["no-fix"]["product_diff_files"])
        self.assertFalse(files["decision-example"]["actual_approval"])
        self.assertFalse(files["review-example"]["actual_review"])
        conflated = dict(scenario, repair_scope=scenario["observation_scope"])
        with self.assertRaisesRegex(ValueError, "does not grant repair"):
            check_synthetic_fixture(conflated, files)
        expired = copy.deepcopy(files)
        expired["unknown"]["observed_at"] = "2026-01-01T00:06:00Z"
        with self.assertRaisesRegex(ValueError, "outside authorized window"):
            check_synthetic_fixture(scenario, expired)
        duplicate = copy.deepcopy(scenario)
        duplicate["open_event_routes"][1]["action"] = "new-repair"
        with self.assertRaisesRegex(ValueError, "update the same issue"):
            check_synthetic_fixture(duplicate, files)
        fake_fix = copy.deepcopy(files)
        fake_fix["no-fix"]["product_diff_files"] = 1
        fake_fix["no-fix"]["delivery_receipt"] = "invented-merge"
        with self.assertRaisesRegex(ValueError, "cannot claim code delivery"):
            check_synthetic_fixture(scenario, fake_fix)

    def test_checkpoint_status_and_reconcile_preserve_claim(self):
        project = self.consumer(suffix="-resume")
        git = self.cli("git", "init", "-q", "-b", "main", cwd=project)
        self.assertEqual(0, git.returncode, git.stderr[-1200:])
        add = self.cli("git", "add", "-A", cwd=project)
        self.assertEqual(0, add.returncode, add.stderr[-1200:])
        commit = self.cli("git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                          "commit", "-q", "-m", "fixture baseline", cwd=project)
        self.assertEqual(0, commit.returncode, commit.stderr[-1200:])
        state = ROOT / "skills/software-factory/scripts/state.py"
        initialize = self.cli(PYTHON, "-I", "-B", state, "init", "--workspace", project,
                              "--program", "demo", "--tracker", "TASKS.md", "--principles", "PRINCIPLES.md")
        self.assertEqual(0, initialize.returncode, initialize.stderr[-1200:])
        claimed = self.cli(PYTHON, "-I", "-B", state, "claim", "--workspace", project,
                           "--task", "demo/name", "--owner", "fixture-worker", "--repo", project,
                           "--paths", "greet.py")
        self.assertEqual(0, claimed.returncode, claimed.stderr[-1200:])
        notes = self.base / "checkpoint-notes.json"
        notes.write_text(json.dumps({"objective": "finish local greeting", "next": "reconcile existing claim",
                                     "completed": ["fixture baseline committed"], "decisions": ["synthetic local scope"],
                                     "open_questions": ["owner acceptance absent"]}))
        checkpoint = self.cli(PYTHON, "-I", "-B", state, "checkpoint", "--workspace", project, "--notes", notes)
        self.assertEqual(0, checkpoint.returncode, checkpoint.stderr[-1200:])
        before = support.tree_hashes(project)
        for command in ("status", "reconcile", "audit"):
            observed = self.cli(PYTHON, "-I", "-B", state, command, "--workspace", project)
            self.assertEqual(0, observed.returncode, observed.stderr[-1200:])
            self.assertEqual(before, support.tree_hashes(project), command)
        active = json.loads((project / ".software-factory/runs/demo/run.json").read_text())
        self.assertEqual("fixture-worker", active["claims"]["demo/name"]["owner"])

    def test_nine_diagrams_have_sources_renders_and_text(self):
        directory = DOCS / "diagrams"
        sources = sorted(directory.glob("*.mmd"))
        self.assertEqual(9, len(sources))
        prose = (directory / "README.md").read_text()
        for source in sources:
            self.assertGreater(len(source.read_text().splitlines()), 6)
            self.assertIn(f"[{source.name}]({source.name})", prose)
            render = source.with_suffix(".svg")
            self.assertTrue(render.is_file())
            self.assertEqual("svg", ET.parse(render).getroot().tag.rsplit("}", 1)[-1])


if __name__ == "__main__":
    unittest.main()
