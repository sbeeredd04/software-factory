"""Crawl skill tests: the deterministic read-only codebase crawl.

Covers the VAL-CRAWL contract area: a stdlib-only deterministic script that
maps a repository (full AST treatment for Python, documented best effort for
JavaScript/TypeScript), writes the regenerable CODEBASE.md artifact with
stated limits, degrades honestly, and never mutates the crawled tree beyond
the single artifact.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def crawler():
    spec = importlib.util.spec_from_file_location("crawl_under_test", CRAWL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name).resolve()
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        return support.Workspace.git(self.root, *args)

    def put(self, rel, text="X = 1\n"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def report(self, root=None, max_files=5000):
        return crawler().crawl(root or self.root, max_files)

    def paths(self, report):
        return {item["path"] for item in report["python"]["modules"]}

    def test_installed_copies_excluded_user_host_code_and_new_files_preserved(self):
        # A negated file needs its directory visible to Git.
        self.put(".gitignore", "/.agents/skills/\n/_bmad/\nignored/*\n!ignored/keep.py\n")
        self.put("app.py")
        self.put(".agents/user.py")
        self.put(".agents/skills/owned.py")
        self.git("add", "-f", ".agents/skills/owned.py")
        self.git("add", "app.py", ".agents/user.py", ".gitignore")
        for rel in (".agents/skills/generated.py", "_bmad/helper.py", "ignored/no.py",
                    "local/install.py"):
            self.put(rel)
        with (self.root / ".git/info/exclude").open("a") as handle:
            handle.write("\n/local/\n")
        self.put("ignored/keep.py")
        self.put("fresh code.py")
        report = self.report()
        self.assertEqual(self.paths(report), {
            "app.py", ".agents/user.py", ".agents/skills/owned.py",
            "ignored/keep.py", "fresh code.py",
        })
        self.assertEqual(report["source"]["selection"], "git-tracked-and-unignored")
        self.assertEqual(report, self.report())

    def test_nested_root_and_nul_delimited_unusual_names(self):
        self.put("outside.py")
        expected = {"a space.py", "a\nline.py", "tab\tname.py", "unicode-λ.py"}
        for rel in expected:
            self.put("nested/" + rel)
        self.git("add", "-A")
        self.assertEqual(self.paths(self.report(self.root / "nested")), expected)

    def test_linked_worktree_uses_shared_excludes_and_tracked_ignored_paths(self):
        self.put("app.py")
        self.git("add", "-A")
        self.git("-c", f"user.email={support.FIXTURE_EMAIL}", "-c",
                 f"user.name={support.FIXTURE_NAME}", "commit", "-qm", "fixture")
        linked = self.tmp / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        with (self.root / ".git/info/exclude").open("a") as handle:
            handle.write("\n/.agents/skills/\n")
        generated = linked / ".agents/skills/generated.py"
        generated.parent.mkdir(parents=True)
        generated.write_text("X = 1\n")
        self.assertEqual(self.paths(self.report(linked)), {"app.py"})

    def test_actual_nested_repository_is_a_reported_boundary(self):
        self.put("app.py")
        nested = self.root / "nested"
        nested.mkdir()
        support.Workspace.git(nested, "init", "-q")
        self.put("nested/unseen.py")
        report = self.report()
        self.assertEqual(self.paths(report), {"app.py"})
        self.assertEqual(report["source"]["selection"], "git-tracked-and-unignored")
        self.assertTrue(any("nested repository" in p for p in report["not_determined"]))

    def test_packaging_obeys_inventory_and_safety_bounds(self):
        self.put("app.py")
        self.put("main.js")
        self.put(".gitignore", "pyproject.toml\npackage.json\n")
        self.put("pyproject.toml", '[project.scripts]\nrun = "app:main"\n')
        self.put("package.json", '{"main":"main.js"}')
        self.assertEqual(self.report()["entry_points"], [])
        self.git("add", "-f", "pyproject.toml", "package.json")
        self.assertEqual({entry["kind"] for entry in self.report()["entry_points"]},
                         {"pyproject-script", "package-json-main"})
        (self.root / "pyproject.toml").unlink()
        (self.root / "package.json").unlink()
        (self.root / "package.json").symlink_to(self.tmp / "foreign.json")
        (self.tmp / "foreign.json").write_text('{"main":"foreign.js"}')
        report = self.report()
        self.assertEqual(report["entry_points"], [])
        self.assertTrue(any("pyproject.toml" in p for p in report["not_determined"]))
        self.assertTrue(any("symlink" in p for p in report["not_determined"]))

    def test_static_bounds_symlinks_caps_and_submodule_boundary(self):
        self.put("a.py")
        self.put("b.py")
        self.put("dist/hidden.py")
        self.git("add", "-f", "dist/hidden.py")
        self.put("large.py", " " * 1_000_001)
        self.put("deleted.py")
        self.git("add", "deleted.py")
        (self.root / "deleted.py").unlink()
        (self.root / "link.py").symlink_to(self.root / "a.py")
        (self.root / "linked").symlink_to(self.tmp, target_is_directory=True)
        module = crawler()
        actual_inventory = module.inventory(self.root)[0]
        # Model gitlink inventory without fetching or executing a submodule.
        (self.root / "submodule").mkdir()
        self.put("submodule/unseen.py")
        with mock.patch.object(module, "inventory", return_value=(
                actual_inventory + ["linked/outside.py", "submodule"],
                "git-tracked-and-unignored", [])):
            report = module.crawl(self.root, 1)
        self.assertEqual(self.paths(report), {"a.py"})
        self.assertEqual(report["source"]["source_files_found"], 2)
        self.assertTrue(report["source"]["cap_reached"])
        for phrase in ("deleted.py", "large.py", "symlink", "submodule"):
            self.assertTrue(any(phrase in p for p in report["not_determined"]), phrase)

    def test_explicit_fallback_never_empty_success_or_private_error(self):
        self.put("app.py")
        self.put(".gitignore", "ignored.py\n")
        self.put("ignored.py")
        module = crawler()
        outcomes = [FileNotFoundError("private sentinel"),
                    subprocess.TimeoutExpired("private sentinel", 10),
                    subprocess.CompletedProcess([], 128, b"", b"private sentinel"),
                    subprocess.CompletedProcess([], 0, b"../escape.py\0", b""),
                    subprocess.CompletedProcess([], 0, b"/escape.py\0", b""),
                    subprocess.CompletedProcess([], 0, b"missing-terminator", b"")]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                options = {"side_effect": outcome} if isinstance(outcome, Exception) else {
                    "return_value": outcome}
                with mock.patch.object(module.subprocess, "run", **options), \
                        mock.patch.object(module, "source_revision", return_value=None):
                    report = module.crawl(self.root, 5000)
                self.assertEqual(self.paths(report), {"app.py", "ignored.py"})
                self.assertEqual(report["source"]["selection"], "filesystem-fallback")
                self.assertIn("filesystem fallback", " ".join(report["not_determined"]))
                self.assertNotIn("private sentinel", json.dumps(report))

    def test_nongit_fallback_is_explicit(self):
        root = self.tmp / "plain"
        root.mkdir()
        (root / "app.py").write_text("X = 1\n")
        report = self.report(root)
        self.assertEqual(self.paths(report), {"app.py"})
        self.assertEqual(report["source"]["selection"], "filesystem-fallback")

    def test_inventory_deduplicates_nul_paths_and_has_literal_readonly_argv(self):
        module = crawler()
        with mock.patch.object(module.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 0, b"app.py\0app.py\0", b"")) as run:
            self.assertEqual(module.inventory(self.root)[0], ["app.py"])
        self.assertEqual(run.call_args.args[0], [
            "git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C",
            str(self.root), "ls-files", "--cached", "--others", "--exclude-standard",
            "-z", "--", ".",
        ])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_path_guards_no_host_cli_or_project_execution_and_no_tree_mutation(self):
        self.put("app.py", 'raise RuntimeError("must never execute")\n')
        self.git("add", "app.py")
        guards = self.tmp / "guards"
        guards.mkdir()
        marker = self.tmp / "forbidden-called"
        for name in ("claude", "cursor-agent", "codex", "agent", "droid"):
            path = guards / name
            path.write_text(f'#!/bin/sh\nprintf called > "{marker}"\nexit 99\n')
            path.chmod(0o755)
        before = tree_hashes(self.root)
        with mock.patch.dict(os.environ, {"PATH": str(guards) + os.pathsep + os.environ["PATH"]}):
            result = run_crawl(self.root, "--artifact", self.tmp / "CB.md",
                               "--json", self.tmp / "report.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(tree_hashes(self.root), before)

    def test_git_fsmonitor_is_not_executed(self):
        self.put("app.py")
        self.git("add", "app.py")
        marker = self.tmp / "monitor-called"
        monitor = self.tmp / "monitor"
        monitor.write_text(f'#!/bin/sh\nprintf called > "{marker}"\nexit 1\n')
        monitor.chmod(0o755)
        self.git("config", "core.fsmonitor", str(monitor))
        self.assertEqual(self.paths(self.report()), {"app.py"})
        self.assertFalse(marker.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX named pipes")
    def test_fallback_never_reads_nonregular_source(self):
        root = self.tmp / "plain"
        root.mkdir()
        (root / "app.py").write_text("X = 1\n")
        os.mkfifo(root / "pipe.py")
        report = self.report(root)
        self.assertEqual(self.paths(report), {"app.py"})
        self.assertIn("non-regular file", " ".join(report["not_determined"]))


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
