"""Tests for the repository validation tooling in scripts/.

Fixtures are tiny synthetic pack trees built under tempdirs. Strings that
resemble private data or secrets are assembled by concatenation so this file
itself stays clean under scripts/scan_public.py.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "scripts"
NETWORK_OK = os.environ.get("SF_SKIP_NETWORK") != "1"
needs_network = unittest.skipUnless(NETWORK_OK, "network-marked check")

SKILLS = (
    "software-factory",
    "sf-help",
    "sf-agents",
    "sf-evolve",
    "sf-eval",
    "sf-principles",
    "sf-crawl",
    "sf-design",
    "sf-smell-audit",
    "sf-refactor",
    "sf-patterns",
)
AGENTS = (
    "sf-product-manager",
    "sf-architect",
    "sf-design-reviewer",
    "sf-engineer",
    "sf-principal-engineer",
    "sf-qa-engineer",
    "sf-code-reviewer",
    "sf-evaluator",
    "sf-ai-engineer",
    "sf-release-engineer",
    "sf-security-reviewer",
)

SYNTHETIC_TERM = "zzq9syntheticterm"


def run_tool(script, *args, cwd=REPO, env=None, stdin=None, timeout=180):
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *(str(a) for a in args)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )


def skill_text(name, *, description="Does fixture work.", body_lines=3):
    lines = [
        "---",
        f"name: {name}",
        f'description: "{description}"',
        "license: MIT",
        "compatibility: fixture",
        "metadata:",
        "  release: v0.1",
        "---",
        "",
        f"# {name}",
        "",
    ]
    lines.extend(f"Fixture body line {index}." for index in range(body_lines))
    return "\n".join(lines) + "\n"


def agent_text(name, *, model="inherit"):
    lines = [
        "---",
        f"name: {name}",
        'description: "Fixture role."',
    ]
    if model is not None:
        lines.append(f"model: {model}")
    lines.extend(["---", "", f"# {name}", ""])
    return "\n".join(lines) + "\n"


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )


class Fixture:
    """A minimal valid pack tree inside a temporary git repository."""

    def __init__(self, test):
        self.temp = tempfile.TemporaryDirectory()
        test.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in SKILLS:
            self.write_skill(name)
        for name in AGENTS:
            self.write_agent(name)
        self.commit()

    def write_skill(self, name, text=None):
        path = self.root / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else skill_text(name))
        return path

    def write_agent(self, name, text=None):
        path = self.root / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else agent_text(name))
        return path

    def commit(self):
        if not (self.root / ".git").exists():
            git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")

    def validate(self):
        return run_tool("validate.py", "--root", self.root)


class ValidateCleanRepoTest(unittest.TestCase):
    def test_repository_tree_validates(self):
        result = run_tool("validate.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("11 skills", result.stdout)
        self.assertIn("11 agents", result.stdout)


class ValidateLayoutTest(unittest.TestCase):
    def test_clean_fixture_passes(self):
        fixture = Fixture(self)
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("11 skills", result.stdout)
        self.assertIn("11 agents", result.stdout)

    def assert_violation(self, fixture, needle):
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(needle, output)

    def test_missing_skill_folder(self):
        fixture = Fixture(self)
        skill = fixture.root / "skills" / "sf-help"
        for path in skill.rglob("*"):
            if path.is_file():
                path.unlink()
        skill.rmdir()
        fixture.commit()
        self.assert_violation(fixture, "sf-help")

    def test_skill_folder_without_skill_md(self):
        fixture = Fixture(self)
        (fixture.root / "skills" / "sf-help" / "SKILL.md").unlink()
        reference = fixture.root / "skills" / "sf-help" / "references" / "x.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("# stray reference\n")
        fixture.commit()
        self.assert_violation(fixture, "sf-help")

    def test_extra_skill_folder(self):
        fixture = Fixture(self)
        fixture.write_skill("sf-zzz")
        fixture.commit()
        self.assert_violation(fixture, "sf-zzz")

    def test_extra_agent_file(self):
        fixture = Fixture(self)
        fixture.write_agent("sf-zzz")
        fixture.commit()
        self.assert_violation(fixture, "sf-zzz")

    def test_missing_agent(self):
        fixture = Fixture(self)
        (fixture.root / "agents" / "sf-evaluator.md").unlink()
        fixture.commit()
        self.assert_violation(fixture, "sf-evaluator")


class ValidateFrontmatterTest(unittest.TestCase):
    def assert_violation(self, fixture, needle):
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(needle, output)

    def test_name_must_match_folder(self):
        fixture = Fixture(self)
        fixture.write_skill("sf-help", skill_text("sf-other"))
        self.assert_violation(fixture, "sf-help")

    def test_entry_skill_line_budget(self):
        fixture = Fixture(self)
        fixture.write_skill("software-factory", skill_text("software-factory", body_lines=160))
        self.assert_violation(fixture, "150")

    def test_other_skill_line_budget(self):
        fixture = Fixture(self)
        fixture.write_skill("sf-help", skill_text("sf-help", body_lines=500))
        self.assert_violation(fixture, "500")

    def test_description_budget(self):
        fixture = Fixture(self)
        fixture.write_skill("sf-help", skill_text("sf-help", description="x" * 301))
        self.assert_violation(fixture, "300")

    def test_description_empty(self):
        fixture = Fixture(self)
        fixture.write_skill("sf-help", skill_text("sf-help", description=""))
        self.assert_violation(fixture, "description")

    def test_nonstandard_key(self):
        fixture = Fixture(self)
        text = skill_text("sf-help").replace("license: MIT", "license: MIT\ncustom-key: nope")
        fixture.write_skill("sf-help", text)
        self.assert_violation(fixture, "custom-key")

    def test_metadata_value_must_be_string(self):
        fixture = Fixture(self)
        text = skill_text("sf-help").replace("  release: v0.1", "  release: 2")
        fixture.write_skill("sf-help", text)
        self.assert_violation(fixture, "release")

    def test_projection_key_rejected_in_skill(self):
        fixture = Fixture(self)
        text = skill_text("sf-help").replace(
            "license: MIT", 'license: MIT\nargument-hint: "<request>"'
        )
        fixture.write_skill("sf-help", text)
        self.assert_violation(fixture, "argument-hint")

    def test_unquoted_colon_description_gets_quoting_hint(self):
        fixture = Fixture(self)
        text = skill_text("sf-help").replace(
            'description: "Does fixture work."',
            "description: Runs things: badly",
        )
        fixture.write_skill("sf-help", text)
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("quote", output.lower())
        self.assertIn("mapping values are not allowed here", output)

    def test_agent_must_inherit_model(self):
        fixture = Fixture(self)
        fixture.write_agent("sf-engineer", agent_text("sf-engineer", model=None))
        self.assert_violation(fixture, "sf-engineer")

    def test_agent_isolation_rejected(self):
        fixture = Fixture(self)
        text = agent_text("sf-engineer") .replace(
            "model: inherit", "model: inherit\nisolation: worktree"
        )
        fixture.write_agent("sf-engineer", text)
        self.assert_violation(fixture, "isolation")


class ValidateReferencesAndManifestsTest(unittest.TestCase):
    def assert_violation(self, fixture, needle):
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(needle, output)

    def test_missing_reference_link(self):
        fixture = Fixture(self)
        text = skill_text("sf-help") + "\nSee [missing](references/nope.md).\n"
        fixture.write_skill("sf-help", text)
        self.assert_violation(fixture, "references/nope.md")

    def test_existing_reference_link_passes(self):
        fixture = Fixture(self)
        reference = fixture.root / "skills" / "sf-help" / "references" / "ok.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("# fine\n")
        text = skill_text("sf-help") + "\nSee [ok](references/ok.md).\n"
        fixture.write_skill("sf-help", text)
        fixture.commit()
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manifest_must_parse(self):
        fixture = Fixture(self)
        (fixture.root / "plugin.json").write_text("{not json")
        fixture.commit()
        self.assert_violation(fixture, "plugin.json")

    def test_manifest_path_outside_root(self):
        fixture = Fixture(self)
        (fixture.root / "plugin.json").write_text('{"icon": "../outside.png"}')
        fixture.commit()
        self.assert_violation(fixture, "outside")

    def test_manifest_missing_path(self):
        fixture = Fixture(self)
        (fixture.root / "plugin.json").write_text('{"skills": ["./skills/sf-nope/"]}')
        fixture.commit()
        self.assert_violation(fixture, "sf-nope")

    def test_manifest_valid_paths_pass(self):
        fixture = Fixture(self)
        (fixture.root / "plugin.json").write_text('{"skills": ["./skills/sf-help/"]}')
        fixture.commit()
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ValidateOfflineTest(unittest.TestCase):
    def test_no_network_or_model_cli_in_source(self):
        source = (TOOLS / "validate.py").read_text()
        for forbidden in ("urllib", "socket", "http", "requests"):
            self.assertNotIn(forbidden, source)


class ScanFixture:
    def __init__(self, test, files, denylist_terms=(SYNTHETIC_TERM,)):
        self.temp = tempfile.TemporaryDirectory()
        test.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for relative, content in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")
        self.denylist = self.root / "denylist.sha256"
        lines = ["# fixture denylist"]
        lines.extend(
            hashlib.sha256(term.encode()).hexdigest() for term in denylist_terms
        )
        self.denylist.write_text("\n".join(lines) + "\n")

    def scan(self, *args, stdin=None, env=None):
        return run_tool(
            "scan_public.py",
            "--root",
            self.root,
            "--denylist",
            self.denylist,
            *args,
            stdin=stdin,
            env=env,
        )


class ScanPublicTest(unittest.TestCase):
    def test_clean_repository_passes(self):
        result = run_tool("scan_public.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout.lower())

    def test_real_denylist_contains_only_digests_and_comments(self):
        lines = (TOOLS / "denylist.sha256").read_text().splitlines()
        entries = [
            line.strip() for line in lines if line.strip() and not line.startswith("#")
        ]
        self.assertTrue(entries, "denylist must not be empty")
        for entry in entries:
            self.assertRegex(entry, r"^[0-9a-f]{64}$")

    def test_planted_denylist_term_flags_with_hashed_display(self):
        fixture = ScanFixture(self, {"notes.md": f"mentions {SYNTHETIC_TERM} here\n"})
        result = fixture.scan()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("notes.md:1", output)
        digest = hashlib.sha256(SYNTHETIC_TERM.encode()).hexdigest()
        self.assertIn(digest, output)
        self.assertNotIn(SYNTHETIC_TERM, output)

    def test_untracked_and_git_internal_files_are_not_scanned(self):
        fixture = ScanFixture(self, {"clean.md": "nothing here\n"})
        (fixture.root / "untracked.md").write_text(f"mentions {SYNTHETIC_TERM}\n")
        (fixture.root / ".git" / "planted").write_text(f"mentions {SYNTHETIC_TERM}\n")
        result = fixture.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_denylist_fails_closed(self):
        fixture = ScanFixture(self, {"clean.md": "nothing here\n"})
        fixture.denylist.unlink()
        result = fixture.scan()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("denylist", output.lower())

    def test_malformed_denylist_fails_closed(self):
        fixture = ScanFixture(self, {"clean.md": "nothing here\n"})
        fixture.denylist.write_text("not-a-digest\n")
        result = fixture.scan()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_users_path_flagged(self):
        fixture = ScanFixture(
            self, {"doc.md": "see " + "/Users/" + "casey/project for details\n"}
        )
        result = fixture.scan()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("doc.md:1", output)
        self.assertNotIn("casey", output)

    def test_home_path_flagged(self):
        fixture = ScanFixture(self, {"doc.md": "see " + "/home/" + "casey/project\n"})
        result = fixture.scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_windows_user_path_flagged(self):
        fixture = ScanFixture(self, {"doc.md": "see C:\\Users\\casey\\file\n"})
        result = fixture.scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_long_token_flagged_short_synthetic_not(self):
        long_token = "ghp_" + "a1" * 12
        fixture = ScanFixture(self, {"leak.txt": f"token: {long_token}\n"})
        self.assertEqual(fixture.scan().returncode, 1)
        clean = ScanFixture(self, {"ok.py": 'short = "ghp_fix01"\n'})
        self.assertEqual(clean.scan().returncode, 0, clean.scan().stdout)

    def test_short_synthetic_sk_token_not_flagged(self):
        fixture = ScanFixture(self, {"ok.py": 'secret = "sk-ant-fix01"\n'})
        self.assertEqual(fixture.scan().returncode, 0, fixture.scan().stdout)

    def test_long_sk_token_flagged(self):
        fixture = ScanFixture(self, {"leak.txt": "sk-ant-" + "a" * 20 + "\n"})
        self.assertEqual(fixture.scan().returncode, 1)

    def test_private_key_header_alone_not_flagged(self):
        fixture = ScanFixture(
            self, {"ok.py": 'pattern = "-----BEGIN FIXTURE PRIVATE KEY-----"\n'}
        )
        self.assertEqual(fixture.scan().returncode, 0, fixture.scan().stdout)

    def test_private_key_block_with_body_flagged(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\n" + "A" * 40 + "\n-----END\n"
        fixture = ScanFixture(self, {"leak.pem": content})
        self.assertEqual(fixture.scan().returncode, 1)

    def test_aws_key_shape_flagged(self):
        fixture = ScanFixture(self, {"leak.txt": "AKIA" + "A1" * 8 + "\n"})
        self.assertEqual(fixture.scan().returncode, 1)

    def test_private_domain_shapes_flagged(self):
        fixture = ScanFixture(
            self, {"leak.txt": "host abc123def456" + ".supabase.co\n"}
        )
        self.assertEqual(fixture.scan().returncode, 1)
        rail = ScanFixture(self, {"leak.txt": "host myapp" + ".up.railway.app\n"})
        self.assertEqual(rail.scan().returncode, 1)

    def test_stdin_mode(self):
        fixture = ScanFixture(self, {"clean.md": "nothing here\n"})
        result = fixture.scan("--stdin", stdin=f"a line with {SYNTHETIC_TERM}\n")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("<stdin>:1", output)

    def test_stdin_mode_clean(self):
        fixture = ScanFixture(self, {"clean.md": "nothing here\n"})
        result = fixture.scan("--stdin", stdin="perfectly fine\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CheckLinksTest(unittest.TestCase):
    def make_tree(self, files):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return root

    def check(self, root):
        return run_tool("check_links.py", "--root", root)

    def test_clean_repository_passes(self):
        result = run_tool("check_links.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_relative_link_and_anchor(self):
        root = self.make_tree(
            {
                "a.md": "# A\n\nSee [b](b.md#target-section) and [self](#a).\n",
                "b.md": "# B\n\n## Target Section\n\ntext\n",
            }
        )
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_broken_relative_link(self):
        root = self.make_tree({"a.md": "# A\n\nSee [gone](missing.md).\n"})
        result = self.check(root)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("a.md", output)
        self.assertIn("missing.md", output)

    def test_dangling_anchor(self):
        root = self.make_tree({"a.md": "# A\n\nSee [anchor](#no-such-anchor).\n"})
        result = self.check(root)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("no-such-anchor", output)

    def test_dangling_cross_file_anchor(self):
        root = self.make_tree(
            {"a.md": "# A\n[b](b.md#nope)\n", "b.md": "# B\n## Real\n"}
        )
        result = self.check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_dead_external_link_is_advisory_only(self):
        root = self.make_tree(
            {"a.md": "# A\n\nSee [x](https://nonexistent.invalid/never).\n"}
        )
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_links_inside_code_fences_ignored(self):
        root = self.make_tree({"a.md": "# A\n\n```\n[example](missing.md)\n```\n"})
        result = self.check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CheckMermaidTest(unittest.TestCase):
    def make_tree(self, files):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return root

    def test_renderer_unavailable_never_passes(self):
        root = self.make_tree({"d.md": "# D\n\n```mermaid\nflowchart TD\n  A --> B\n```\n"})
        stub = Path(tempfile.mkdtemp(prefix="sf-bare-path-"))
        env = {"PATH": str(stub), "HOME": os.environ.get("HOME", "")}
        result = run_tool("check_mermaid.py", "--root", root, env=env)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("unverified", output.lower())

    @needs_network
    def test_valid_diagram_renders(self):
        root = self.make_tree({"d.md": "# D\n\n```mermaid\nflowchart TD\n  A --> B\n```\n"})
        result = run_tool("check_mermaid.py", "--root", root, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rendered", result.stdout)

    @needs_network
    def test_broken_diagram_fails(self):
        root = self.make_tree({"d.md": "# D\n\n```mermaid\nnot a diagram @@@\n```\n"})
        result = run_tool("check_mermaid.py", "--root", root, timeout=600)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("d.md", output)

    @needs_network
    def test_repository_diagrams_render(self):
        result = run_tool("check_mermaid.py", timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CheckAllShTest(unittest.TestCase):
    def test_gate_script_lists_every_step(self):
        script = (TOOLS / "check_all.sh").read_text()
        for needle in (
            "python3 -m compileall",
            "python3 -m unittest discover -s tests -v",
            "uvx ruff check .",
            "shellcheck",
            "install.sh",
            "python3 scripts/validate.py",
            "python3 scripts/scan_public.py",
            "python3 scripts/check_links.py",
            "python3 scripts/check_mermaid.py",
            "agentskills validate",
            "check-jsonschema",
            "vendor.github-workflows",
            "vendor.github-issue-forms",
        ):
            self.assertIn(needle, script)

    def test_gate_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", str(TOOLS / "check_all.sh")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class ExternalValidatorsTest(unittest.TestCase):
    @needs_network
    def test_agentskills_validate_accepts_every_skill(self):
        for name in SKILLS:
            result = subprocess.run(
                ["uvx", "--from", "skills-ref", "agentskills", "validate", f"skills/{name}"],
                capture_output=True,
                text=True,
                cwd=REPO,
                timeout=300,
                check=False,
            )
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, f"{name}: {output}")
            self.assertIn("Valid skill", output)

    @needs_network
    def test_github_yaml_schemas_validate(self):
        workflows = subprocess.run(
            ["uvx", "check-jsonschema", "--builtin-schema",
             "vendor.github-workflows", ".github/workflows/ci.yml"],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=300,
            check=False,
        )
        self.assertEqual(workflows.returncode, 0, workflows.stdout + workflows.stderr)
        forms = subprocess.run(
            ["uvx", "check-jsonschema", "--builtin-schema",
             "vendor.github-issue-forms", ".github/ISSUE_TEMPLATE/bug_report.yml",
             ".github/ISSUE_TEMPLATE/feature_request.yml",
             ".github/ISSUE_TEMPLATE/skill_contribution.yml"],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=300,
            check=False,
        )
        self.assertEqual(forms.returncode, 0, forms.stdout + forms.stderr)


if __name__ == "__main__":
    unittest.main()
