"""Crawl skill tests: the deterministic read-only codebase crawl.

Covers the VAL-CRAWL contract area: a stdlib-only deterministic script that
maps a repository (full AST treatment for Python, documented best effort for
JavaScript/TypeScript), writes the regenerable CODEBASE.md artifact with
stated limits, degrades honestly, and never mutates the crawled tree beyond
the single artifact.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

REPO = support.REPO
CRAWL = REPO / "skills" / "sf-crawl" / "scripts" / "crawl.py"
FIXTURES = REPO / "tests" / "fixtures" / "repos"
PY_FIXTURE = FIXTURES / "python-cli"
TS_FIXTURE = FIXTURES / "typescript-web"
GREEN_FIXTURE = FIXTURES / "greenfield"


def run_crawl(*args, timeout=120):
    """Run the crawl CLI exactly the way a validator would."""
    return subprocess.run(
        [sys.executable, str(CRAWL), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def tree_hashes(root: Path) -> dict[str, str]:
    """Map of relative path to sha256 for every file under root."""
    hashes = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def normalize_artifact(text: str) -> str:
    """Strip the two declared volatile header fields for idempotence checks."""
    lines = [
        line
        for line in text.splitlines()
        if not line.startswith("- Source revision:") and not line.startswith("- Generated:")
    ]
    return "\n".join(lines)


class CrawlerSourceChecks(unittest.TestCase):
    def test_stdlib_only(self):
        self.assertEqual(support.non_stdlib_imports(CRAWL), [])

    def test_no_agent_cli_or_network(self):
        import ast

        text = CRAWL.read_text(encoding="utf-8")
        for needle in ("urllib", "socket", "http.client", "requests"):
            self.assertNotIn(needle, text)
        # The only permitted subprocess is read-only git plumbing.
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                continue
            argv = node.args[0]
            self.assertIsInstance(argv, ast.List)
            self.assertEqual(
                ast.literal_eval(argv.elts[0]),
                "git",
                "crawl.py may only spawn read-only git",
            )


class PythonFixtureCrawl(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.json_path = self.tmp / "report.json"
        self.artifact = self.tmp / "CODEBASE.md"
        self.result = run_crawl(
            PY_FIXTURE, "--json", self.json_path, "--artifact", self.artifact
        )
        assert self.result.returncode == 0, self.result.stderr
        self.report = json.loads(self.json_path.read_text())

    def modules(self):
        return {m["name"]: m for m in self.report["python"]["modules"]}

    def test_exit_zero_and_valid_json(self):
        self.assertEqual(self.report["schema"], "sf-crawl/1")

    def test_module_map_is_fixture_accurate(self):
        names = set(self.modules())
        self.assertEqual(
            names,
            {
                "fixture_cli",
                "fixture_cli.cli",
                "fixture_cli.core",
                "fixture_cli.__main__",
            },
        )
        cli = self.modules()["fixture_cli.cli"]
        self.assertEqual(cli["path"], "fixture_cli/cli.py")
        self.assertIn(
            {"name": "main", "kind": "function", "line": 6}, cli["definitions"]
        )

    def test_import_edges_internal_vs_other(self):
        cli = self.modules()["fixture_cli.cli"]
        self.assertEqual(cli["internal_imports"], ["fixture_cli.core"])
        self.assertEqual(cli["other_imports"], [])
        core = self.modules()["fixture_cli.core"]
        self.assertEqual(core["internal_imports"], [])
        self.assertEqual(core["other_imports"], ["json"])

    def test_call_edges_extracted_and_resolved(self):
        cli = self.modules()["fixture_cli.cli"]
        (main_calls,) = [c for c in cli["calls"] if c["function"] == "main"]
        self.assertIn("Engine", main_calls["calls"])
        self.assertIn("print", main_calls["calls"])
        self.assertEqual(
            main_calls["resolved"], {"Engine": "fixture_cli.core.Engine"}
        )
        core = self.modules()["fixture_cli.core"]
        render = [c for c in core["calls"] if c["function"] == "Engine.render"]
        self.assertEqual(len(render), 1)
        self.assertEqual(
            render[0]["resolved"],
            {"format_payload": "fixture_cli.core.format_payload"},
        )

    def test_entry_points_detected(self):
        kinds = {(e["kind"], e.get("path") or e.get("name")) for e in self.report["entry_points"]}
        self.assertIn(("pyproject-script", "fixture-cli"), kinds)
        self.assertIn(("python-main-guard", "fixture_cli/cli.py"), kinds)
        self.assertIn(("python-dunder-main", "fixture_cli/__main__.py"), kinds)

    def test_nothing_unparsed(self):
        self.assertEqual(self.report["python"]["unparsed"], [])

    def test_artifact_sections_and_marking(self):
        text = self.artifact.read_text()
        for section in (
            "## Limits",
            "## Module map (Python)",
            "## Import edges (Python)",
            "## Call edges (Python)",
            "## Entry points",
            "## Not determined",
        ):
            self.assertIn(section, text)
        self.assertIn("fixture_cli.cli", text)
        self.assertIn("confirmed:", text)
        self.assertIn("best effort", text.lower())
        # The crawled tree root must never leak into the artifact.
        self.assertNotIn(str(PY_FIXTURE), text)
        self.assertNotIn("/Users/", text)


class Determinism(unittest.TestCase):
    def test_two_runs_identical_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for name in ("a.json", "b.json"):
                out = Path(tmp) / name
                result = run_crawl(
                    PY_FIXTURE, "--json", out, "--artifact", Path(tmp) / "CB.md"
                )
                assert result.returncode == 0, result.stderr
                outputs.append(out.read_bytes())
            self.assertEqual(outputs[0], outputs[1])

    def test_artifact_idempotent_but_declared_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "CODEBASE.md"
            texts = []
            for _ in range(2):
                result = run_crawl(TS_FIXTURE, "--artifact", artifact)
                assert result.returncode == 0, result.stderr
                texts.append(artifact.read_text())
            self.assertEqual(
                normalize_artifact(texts[0]), normalize_artifact(texts[1])
            )
            self.assertIn("- Source revision:", texts[0])
            self.assertIn("- Generated:", texts[0])

    def test_fixture_trees_unchanged_by_crawl(self):
        for fixture in (PY_FIXTURE, TS_FIXTURE, GREEN_FIXTURE):
            before = tree_hashes(fixture)
            with tempfile.TemporaryDirectory() as tmp:
                result = run_crawl(
                    fixture,
                    "--json",
                    Path(tmp) / "r.json",
                    "--artifact",
                    Path(tmp) / "CB.md",
                )
                assert result.returncode == 0, result.stderr
            self.assertEqual(before, tree_hashes(fixture))


class BestEffortAndEmptyTrees(unittest.TestCase):
    def test_typescript_best_effort(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            artifact = Path(tmp) / "CODEBASE.md"
            result = run_crawl(TS_FIXTURE, "--json", out, "--artifact", artifact)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            ts_files = {f["path"]: f for f in report["best_effort"]["typescript"]}
            self.assertEqual(
                set(ts_files), {"src/cli.ts", "src/greet.ts", "src/index.ts"}
            )
            self.assertEqual(ts_files["src/index.ts"]["imports"], ["./greet"])
            self.assertEqual(ts_files["src/index.ts"]["exports"], ["main"])
            self.assertEqual(ts_files["src/greet.ts"]["exports"], ["greet"])
            kinds = {e["kind"] for e in report["entry_points"]}
            self.assertIn("package-json-main", kinds)
            self.assertIn("package-json-bin", kinds)
            self.assertEqual(report["python"]["modules"], [])
            text = artifact.read_text()
            self.assertIn("best effort", text.lower())
            self.assertIn("lexical", text.lower())
            self.assertIn("src/index.ts", text)

    def test_greenfield_explicit_empty_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            artifact = Path(tmp) / "CODEBASE.md"
            result = run_crawl(GREEN_FIXTURE, "--json", out, "--artifact", artifact)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["python"]["modules"], [])
            self.assertEqual(report["entry_points"], [])
            text = artifact.read_text()
            for section in (
                "## Module map (Python)",
                "## Import edges (Python)",
                "## Call edges (Python)",
                "## Entry points",
                "## Best effort (JavaScript/TypeScript)",
            ):
                self.assertIn(section, text)
            self.assertIn("No Python source found", text)
            self.assertIn("No entry points detected", text)


class HonestDegradation(unittest.TestCase):
    def test_unparsable_file_reported_others_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "good.py").write_text("X = 1\n")
            (root / "broken.py").write_text("def broken(:\n")
            out = Path(tmp) / "report.json"
            result = run_crawl(root, "--json", out, "--artifact", Path(tmp) / "CB.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertIn("good", {m["name"] for m in report["python"]["modules"]})
            self.assertEqual(len(report["python"]["unparsed"]), 1)
            failure = report["python"]["unparsed"][0]
            self.assertEqual(failure["path"], "broken.py")
            self.assertEqual(failure["error"], "SyntaxError")
            self.assertNotIn(
                "def broken", json.dumps(report), "error detail must not leak source"
            )
            combined = result.stdout + result.stderr
            self.assertNotIn("Traceback", combined)

    def test_missing_root_one_message_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            artifact = Path(tmp) / "CB.md"
            result = run_crawl(missing, "--artifact", artifact)
            self.assertEqual(result.returncode, 2)
            messages = [line for line in result.stderr.splitlines() if line.strip()]
            self.assertEqual(len(messages), 1)
            self.assertTrue(messages[0].startswith("crawl: "))
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(artifact.exists())

    def test_unreadable_directory_reported_repo_relative(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("chmod 000 does not restrict the superuser")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "app.py").write_text('"""App."""\n')
            restricted = root / "restricted"
            restricted.mkdir()
            (restricted / "hidden.py").write_text("X = 1\n")
            restricted.chmod(0o000)
            out = Path(tmp) / "report.json"
            artifact = Path(tmp) / "CB.md"
            try:
                result = run_crawl(root, "--json", out, "--artifact", artifact)
            finally:
                restricted.chmod(0o700)
            # Honest degradation: the entry is named, the rest is kept, exit 0.
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            report = json.loads(out.read_text())
            self.assertIn("app", {m["name"] for m in report["python"]["modules"]})
            named = [p for p in report["not_determined"] if "restricted" in p]
            self.assertTrue(named, report["not_determined"])
            # No absolute, home or leading-slash path may leak into the
            # JSON report or the committed artifact.
            payload = json.dumps(report)
            text = artifact.read_text()
            for needle in (str(root), str(root.resolve()), str(Path.home())):
                self.assertNotIn(needle, payload)
                self.assertNotIn(needle, text)
            for problem in report["not_determined"]:
                self.assertNotRegex(problem, r"(^|[\s(])/")

    def test_file_cap_is_reported_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            for name in ("a_mod.py", "b_mod.py", "c_mod.py"):
                (root / name).write_text(f'"""Module {name}."""\n')
            out = Path(tmp) / "report.json"
            artifact = Path(tmp) / "CB.md"
            result = run_crawl(
                root, "--json", out, "--artifact", artifact, "--max-files", "1"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertTrue(report["source"]["cap_reached"])
            self.assertEqual(report["source"]["source_files_found"], 3)
            self.assertEqual(report["source"]["source_files_parsed"], 1)
            self.assertEqual(len(report["python"]["modules"]), 1)
            self.assertIn("cap", artifact.read_text().lower())


class ArtifactWriteSemantics(unittest.TestCase):
    def test_default_location_single_copy_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "app.py").write_text('"""App."""\n')
            for _ in range(2):
                result = run_crawl(root)
                assert result.returncode == 0, result.stderr
            context = root / ".software-factory" / "context"
            written = [p.name for p in context.iterdir()]
            self.assertEqual(written, ["CODEBASE.md"])
            leftovers = [
                p.relative_to(root).as_posix()
                for p in root.rglob("*")
                if p.is_file()
            ]
            self.assertEqual(
                sorted(leftovers),
                [".software-factory/context/CODEBASE.md", "app.py"],
            )

    def test_revision_recorded_when_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            git = support.Workspace.git
            git(root, "init", "-q", "-b", "main")
            (root / "app.py").write_text('"""App."""\n')
            git(root, "add", "-A")
            git(
                root,
                "-c",
                f"user.email={support.FIXTURE_EMAIL}",
                "-c",
                f"user.name={support.FIXTURE_NAME}",
                "commit",
                "-q",
                "-m",
                "fixture",
            )
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            out = Path(tmp) / "report.json"
            result = run_crawl(root, "--json", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["source"]["revision"], head)
            artifact = root / ".software-factory" / "context" / "CODEBASE.md"
            self.assertIn(head, artifact.read_text())

    def test_unknown_revision_when_not_a_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "app.py").write_text('"""App."""\n')
            out = Path(tmp) / "report.json"
            result = run_crawl(root, "--json", out, "--artifact", Path(tmp) / "CB.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertIsNone(report["source"]["revision"])
            text = (Path(tmp) / "CB.md").read_text()
            self.assertRegex(text, r"Source revision:.*unknown")


if __name__ == "__main__":
    unittest.main()
