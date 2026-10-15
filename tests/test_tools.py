"""Tests for the repository validation tooling in scripts/.

Fixtures are tiny synthetic pack trees built under tempdirs. Strings that
resemble private data or secrets are assembled by concatenation so this file
itself stays clean under scripts/scan_public.py.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        # The success report names every cap class with the measured maximum.
        self.assertIn("budgets:", result.stdout)
        self.assertIn("prose reference", result.stdout)
        self.assertIn("data/catalog/index reference", result.stdout)


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
        # 11 frontmatter/heading lines + 200 body lines = 211 measured lines.
        fixture.write_skill("sf-help", skill_text("sf-help", body_lines=200))
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("120", output)  # the non-entry skill cap
        self.assertIn("211", output)  # the measured value beside the cap

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


class ValidateBudgetsTest(unittest.TestCase):
    """Every cap class is enforced with the cap beside the measured value."""

    def assert_violation(self, fixture, *needles):
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        for needle in needles:
            self.assertIn(needle, output)
        return output

    def write_reference(self, fixture, skill, name, lines):
        path = fixture.root / "skills" / skill / "references" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        body = [f"# {name}", ""] + [f"Reference line {index}." for index in range(lines)]
        path.write_text("\n".join(body) + "\n")
        return path

    def test_entry_skill_over_budget_reports_cap_and_measured(self):
        fixture = Fixture(self)
        # 11 frontmatter/heading lines + 200 body lines = 211 measured lines.
        fixture.write_skill(
            "software-factory", skill_text("software-factory", body_lines=200)
        )
        self.assert_violation(fixture, "150", "211")

    def test_agent_over_budget_reports_cap_and_measured(self):
        fixture = Fixture(self)
        lines = [
            "---",
            "name: sf-engineer",
            'description: "Fixture role."',
            "model: inherit",
            "---",
            "",
            "# sf-engineer",
        ]
        lines.extend(f"Role line {index}." for index in range(63))  # 70 lines
        fixture.write_agent("sf-engineer", "\n".join(lines) + "\n")
        self.assert_violation(fixture, "60", "70")

    def test_agent_description_over_budget_reports_cap(self):
        fixture = Fixture(self)
        text = agent_text("sf-engineer").replace(
            'description: "Fixture role."', f'description: "{"x" * 301}"'
        )
        fixture.write_agent("sf-engineer", text)
        self.assert_violation(fixture, "300", "301")

    def test_prose_reference_over_budget_reports_cap_and_measured(self):
        fixture = Fixture(self)
        # "# notes" + blank + 250 filler lines = 252 measured lines.
        self.write_reference(fixture, "sf-help", "notes.md", 250)
        self.assert_violation(fixture, "prose", "240", "252")

    def test_data_reference_over_budget_reports_cap_and_measured(self):
        fixture = Fixture(self)
        # "sources.md" is a named data/catalog/index file; 332 measured lines.
        self.write_reference(fixture, "sf-help", "sources.md", 330)
        self.assert_violation(fixture, "data/catalog/index", "320", "332")

    def test_references_within_budget_pass(self):
        fixture = Fixture(self)
        self.write_reference(fixture, "sf-help", "notes.md", 100)
        self.write_reference(fixture, "sf-help", "sources.md", 200)
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_success_output_reports_maximum_per_cap_class(self):
        fixture = Fixture(self)
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("budgets:", output)
        self.assertIn("entry skill", output)
        self.assertIn("/150", output)
        self.assertIn("/120", output)
        self.assertIn("/60", output)
        self.assertIn("/240", output)
        self.assertIn("/320", output)


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


class ValidateNativeManifestsTest(unittest.TestCase):
    """Native paths use their owning root, including generated dist output."""

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def native_fixture(self, host):
        fixture = Fixture(self)
        market = fixture.root / "dist" / host
        plugin = market / "plugins" / "sample"
        (plugin / "skills").mkdir(parents=True)
        (plugin / "agents").mkdir()
        (plugin / "agents" / "role.md").write_text("# Native role\n")
        if host == "codex":
            catalog = market / ".agents" / "plugins" / "marketplace.json"
            self.write_json(catalog, {"plugins": [{"source": {
                "source": "local", "path": "./plugins/sample"}}]})
            manifest = self.write_json(plugin / "plugin.json", {"name": "sample"})
        else:
            hidden = ".claude-plugin" if host == "claude-code" else ".cursor-plugin"
            catalog = market / hidden / "marketplace.json"
            self.write_json(catalog, {"plugins": [{"source": "./plugins/sample"}]})
            data = {"skills": ["./skills/"], "agents": ["./agents/role.md"]}
            if host == "cursor":
                (plugin / "rules").mkdir()
                data["rules"] = ["./rules/"]
            manifest = self.write_json(plugin / hidden / "plugin.json", data)
        return fixture, market, plugin, catalog, manifest

    def assert_valid(self, fixture):
        result = fixture.validate()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def assert_invalid(self, fixture, needle):
        result = fixture.validate()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(needle, result.stdout + result.stderr)

    def test_all_native_hidden_bases_under_dist(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                fixture, _, _, _, _ = self.native_fixture(host)
                self.assert_valid(fixture)

    def test_missing_native_components_and_catalog_sources_fail(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                fixture, _, plugin, catalog, manifest = self.native_fixture(host)
                self.assert_valid(fixture)
                self.write_json(catalog, {"source": "./plugins/missing"})
                self.assert_invalid(fixture, "./plugins/missing")
                catalog.unlink()
                if host != "codex":
                    for kind, relative in (("skills", "./missing-skills/"),
                                           ("agents", "./agents/missing.md"),
                                           ("rules", "./missing-rules/")):
                        self.write_json(manifest, {kind: [relative]})
                        self.assert_invalid(fixture, relative)
                self.assertTrue(plugin.is_dir())

    def test_native_component_cannot_escape_its_plugin(self):
        for host in ("claude-code", "cursor"):
            with self.subTest(host=host):
                fixture, _, plugin, _, manifest = self.native_fixture(host)
                outside = plugin.parent / "outside.md"
                outside.write_text("# Outside plugin\n")
                self.write_json(manifest, {"agents": ["../outside.md"]})
                self.assert_invalid(fixture, "outside its manifest root")

    def test_native_catalog_cannot_escape_its_marketplace(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                fixture, market, _, catalog, _ = self.native_fixture(host)
                (market.parent / "outside").mkdir(exist_ok=True)
                self.write_json(catalog, {"source": "../outside"})
                self.assert_invalid(fixture, "outside its manifest root")

    def test_native_symlink_cannot_escape_its_owner(self):
        fixture, _, plugin, _, manifest = self.native_fixture("claude-code")
        target = plugin.parent / "outside.md"
        target.write_text("# Outside plugin\n")
        (plugin / "agents" / "link.md").symlink_to(target)
        self.write_json(manifest, {"agents": ["./agents/link.md"]})
        self.assert_invalid(fixture, "outside its manifest root")

    def test_manifest_and_link_reject_existing_sibling_prefix_collision(self):
        fixture = Fixture(self)
        sibling = fixture.root.with_name(fixture.root.name + "-extra")
        sibling.mkdir()
        self.addCleanup(shutil.rmtree, sibling)
        (sibling / "outside.md").write_text("# Outside root\n")
        relative = "../" + sibling.name + "/outside.md"
        self.write_json(fixture.root / "plugin.json", {"icon": relative})
        self.assert_invalid(fixture, "outside the repository")
        (fixture.root / "plugin.json").unlink()
        link = "../../../" + sibling.name + "/outside.md"
        fixture.write_skill("sf-help", skill_text("sf-help") + f"\n[Outside]({link})\n")
        self.assert_invalid(fixture, "escapes the repository root")

    def test_manifest_symlink_outside_repository_fails(self):
        fixture = Fixture(self)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name).resolve() / "outside.md"
        target.write_text("# Outside\n")
        (fixture.root / "link.md").symlink_to(target)
        self.write_json(fixture.root / "plugin.json", {"icon": "./link.md"})
        self.assert_invalid(fixture, "outside the repository")

    def test_generic_nested_manifests_keep_parent_relative_paths(self):
        fixture = Fixture(self)
        asset = fixture.root / "assets" / "existing.md"
        asset.parent.mkdir()
        asset.write_text("# Existing\n")
        self.write_json(fixture.root / "custom" / "plugin.json",
                        {"icon": "../assets/existing.md"})
        self.write_json(fixture.root / "custom" / "deep" / "marketplace.json",
                        {"source": "../../assets/existing.md"})
        self.assert_valid(fixture)
        asset.unlink()
        self.assert_invalid(fixture, "existing.md")

    def test_malformed_hidden_manifests_fail(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                fixture, _, _, catalog, _ = self.native_fixture(host)
                catalog.write_text("{broken")
                self.assert_invalid(fixture, "manifest does not parse")

    def test_generated_bundles_and_extracted_release_validate(self):
        from support import recorder_env

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        env, records, guard = recorder_env()
        self.addCleanup(shutil.rmtree, records)
        self.addCleanup(shutil.rmtree, guard.parent)
        for name in ("claude-code", "agent", "droid", "gh"):
            stub = guard.parent / name
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$SF_GUARD_LOG"\nexit 127\n')
            stub.chmod(0o755)
        fixture = Fixture(self)
        (fixture.root / "dist").mkdir()
        generated = subprocess.run(
            [sys.executable, "-B", str(REPO / "scripts" / "distribution.py"),
             "--host", "all", "--out", str(fixture.root / "dist" / "native")],
            env=env, capture_output=True, text=True, check=False, timeout=90)
        self.assertEqual(0, generated.returncode, generated.stdout + generated.stderr)
        self.assert_valid(fixture)
        release = base / "release"
        built = run_tool("build_release.py", "--out", release, env=env)
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        extracted = base / "extracted"
        extracted.mkdir()
        with tarfile.open(release / "sf-v0.1.0.tar.gz", "r:gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                target = extracted / member.name
                self.assertTrue(target.resolve().is_relative_to(extracted))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        payload = extracted / "sf-v0.1.0"
        checked = run_tool("validate.py", "--root", payload, env=env)
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        self.assertFalse(guard.exists(), "host or provider CLI invoked")
        self.assertEqual([], list(records.iterdir()), "package or download tool invoked")


class ValidateLegacyNamesTest(unittest.TestCase):
    """Retired pre-rename names must not appear in shipped prose content."""

    def assert_violation(self, fixture, needle):
        result = fixture.validate()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(needle, output)

    def test_clean_fixture_passes(self):
        fixture = Fixture(self)
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_skill_name_flagged(self):
        fixture = Fixture(self)
        text = skill_text("sf-help") + "\nThis replaced the software-design skill.\n"
        fixture.write_skill("sf-help", text)
        self.assert_violation(fixture, "software-design")

    def test_legacy_catalog_names_flagged(self):
        for legacy in (
            "code-smell-audit",
            "refactoring-playbook",
            "design-pattern-judgment",
        ):
            with self.subTest(legacy=legacy):
                fixture = Fixture(self)
                text = skill_text("sf-refactor") + f"\nSee {legacy} for detail.\n"
                fixture.write_skill("sf-refactor", text)
                self.assert_violation(fixture, legacy)

    def test_legacy_role_names_flagged(self):
        for legacy in ("risk-coder", "coder"):
            with self.subTest(legacy=legacy):
                fixture = Fixture(self)
                text = agent_text("sf-engineer") + f"\nFormerly the {legacy} role.\n"
                fixture.write_agent("sf-engineer", text)
                self.assert_violation(fixture, legacy)

    def test_legacy_factory_agent_name_flagged(self):
        fixture = Fixture(self)
        text = agent_text("sf-engineer") + "\nFormerly factory-coder.\n"
        fixture.write_agent("sf-engineer", text)
        self.assert_violation(fixture, "factory-coder")

    def test_legacy_name_in_frontmatter_key_not_flagged(self):
        fixture = Fixture(self)
        text = skill_text("sf-design").replace(
            "  release: v0.1", "  factory-role: design\n  release: v0.1"
        )
        fixture.write_skill("sf-design", text)
        result = fixture.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_names_and_lookalikes_pass(self):
        fixture = Fixture(self)
        text = skill_text("sf-help") + (
            "\nWorks beside sf-design, sf-refactor and the software-factory"
            " entry; the decoder and CodeRabbit integrations stay.\n"
        )
        fixture.write_skill("sf-help", text)
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

    def native_tree(self, host):
        hidden = ".claude-plugin" if host == "claude-code" else ".cursor-plugin"
        market = "dist/" + host
        plugin = market + "/plugins/sample"
        catalog = market + ("/.agents/plugins/marketplace.json" if host == "codex"
                            else "/" + hidden + "/marketplace.json")
        source = ({"source": "local", "path": "./plugins/sample"}
                  if host == "codex" else "./plugins/sample")
        manifest = plugin + ("/plugin.json" if host == "codex"
                             else "/" + hidden + "/plugin.json")
        data = ({"name": "sample"} if host == "codex" else
                {"skills": ["./skills/"], "agents": ["./agents/role.md"]})
        root = self.make_tree({catalog: json.dumps({"plugins": [{"source": source}]}),
                               manifest: json.dumps(data),
                               plugin + "/skills/entry/SKILL.md": "# Skill\n",
                               plugin + "/agents/role.md": "# Role\n"})
        return root, root / market, root / plugin, root / catalog, root / manifest

    def test_native_manifest_and_catalog_bases(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                root, _, _, _, _ = self.native_tree(host)
                result = self.check(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_native_missing_targets_still_fail(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                root, _, _, catalog, _ = self.native_tree(host)
                catalog.write_text(json.dumps({"source": "./plugins/missing"}))
                result = self.check(root)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("./plugins/missing", result.stdout)

    def test_native_owner_escape_and_symlink_fail(self):
        for host in ("claude-code", "cursor", "codex"):
            with self.subTest(host=host):
                root, market, _, catalog, _ = self.native_tree(host)
                outside = market.parent / "outside"
                outside.mkdir(exist_ok=True)
                catalog.write_text(json.dumps({"source": "../outside"}))
                result = self.check(root)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("escapes its manifest root", result.stdout)
                (market / "linked").symlink_to(outside, target_is_directory=True)
                catalog.write_text(json.dumps({"source": "./linked"}))
                result = self.check(root)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("escapes its manifest root", result.stdout)

    def test_native_component_escape_fails(self):
        for host in ("claude-code", "cursor"):
            with self.subTest(host=host):
                root, _, plugin, _, manifest = self.native_tree(host)
                (plugin.parent / "outside.md").write_text("# Outside plugin\n")
                manifest.write_text(json.dumps({"agents": ["../outside.md"]}))
                result = self.check(root)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("escapes its manifest root", result.stdout)

    def test_generic_json_keeps_parent_relative_semantics(self):
        root = self.make_tree({"assets/a.md": "# A\n",
                               "custom/plugin.json": '{"asset":"../assets/a.md"}',
                               "custom/deep/data.json": '{"asset":"../../assets/a.md"}',
                               "custom/.claude-plugin/settings.json": '{"asset":"./local.md"}',
                               "custom/.claude-plugin/local.md": "# Local\n"})
        result = self.check(root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        (root / "assets/a.md").unlink()
        self.assertEqual(1, self.check(root).returncode)

    def test_existing_sibling_prefix_escape_is_rejected(self):
        for kind in ("markdown", "json"):
            with self.subTest(kind=kind):
                root = self.make_tree({"a.md": "# A\n"})
                sibling = root.with_name(root.name + "-extra")
                sibling.mkdir()
                self.addCleanup(shutil.rmtree, sibling)
                (sibling / "outside.md").write_text("# Outside\n")
                target = "../" + sibling.name + "/outside.md"
                if kind == "markdown":
                    (root / "a.md").write_text(f"# A\n[Outside]({target})\n")
                else:
                    (root / "data.json").write_text(json.dumps({"path": target}))
                result = self.check(root)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("escapes the root", result.stdout)

    def test_scope_and_parse_ownership_are_unchanged(self):
        root = self.make_tree({"a.md": "# A\n", "broken.json": "{broken"})
        self.assertEqual(0, self.check(root).returncode)
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        (root / "untracked.json").write_text('{"path":"./missing"}')
        self.assertEqual(0, self.check(root).returncode)
        git(root, "add", "untracked.json")
        self.assertEqual(1, self.check(root).returncode)


class CheckMermaidDiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("check_mermaid", TOOLS / "check_mermaid.py")
        cls.renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.renderer)

    def render_stub(self, *, returncode=1, stdout="", stderr="", output=False):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            if output:
                (workdir / "fixture.svg").write_text("<svg/>")
            result = subprocess.CompletedProcess([], returncode, stdout, stderr)
            with mock.patch.object(self.renderer.subprocess, "run", return_value=result) as run:
                outcome = self.renderer.render("fixture-npx", "flowchart TD\nA --> B", workdir, "fixture")
            args, kwargs = run.call_args
            self.assertEqual(
                ["fixture-npx", "-y", self.renderer.MERMAID_PACKAGE,
                 "-i", str(workdir / "fixture.mmd"), "-o", str(workdir / "fixture.svg")],
                args[0],
            )
            self.assertEqual(self.renderer.RENDER_TIMEOUT, kwargs["timeout"])
            self.assertTrue(kwargs["capture_output"])
            self.assertFalse(kwargs["check"])
            return outcome

    def test_launch_cause_and_both_streams_are_retained(self):
        stderr = "ROOT BROWSER LAUNCH ERROR\n" + "stack frame\n" * 80
        ok, detail = self.render_stub(stdout="renderer context", stderr=stderr)
        self.assertFalse(ok)
        self.assertIn("ROOT BROWSER LAUNCH ERROR", detail)
        self.assertIn("stderr:\n", detail)
        self.assertIn("stdout:\nrenderer context", detail)
        self.assertIn("exit code: 1; output SVG: missing", detail)

    def test_cli_retains_invalid_utf8_renderer_output_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixture.mmd").write_text("graph TD\nA --> B\n")
            stub = root / "npx"
            stub.write_text(
                f"#!{sys.executable}\n"
                "import os\n"
                "os.write(2, b'ROOT BROWSER CAUSE \\xff\\n')\n"
                "os.write(1, b'renderer stdout \\xfe\\n')\n"
                "raise SystemExit(7)\n"
            )
            stub.chmod(0o755)
            env = dict(os.environ, PATH=str(root))
            result = run_tool("check_mermaid.py", root / "fixture.mmd", env=env)
        detail = result.stdout + result.stderr
        self.assertEqual(1, result.returncode, detail)
        self.assertIn("fixture.mmd: diagram failed to render", detail)
        self.assertIn("exit code: 7; output SVG: missing", detail)
        self.assertIn("stderr:\nROOT BROWSER CAUSE \ufffd", detail)
        self.assertIn("stdout:\nrenderer stdout \ufffd", detail)
        self.assertNotIn("UnicodeDecodeError", detail)

    def test_large_streams_keep_head_tail_with_inclusive_byte_bound(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                text = "HEAD-" + "\u20ac" * 10_000 + "-TAIL"
                ok, detail = self.render_stub(**{stream: text})
                self.assertFalse(ok)
                bounded = self.renderer.bounded_output(text)
                self.assertLessEqual(len(bounded.encode("utf-8")), 8 * 1024)
                self.assertTrue(bounded.startswith("HEAD-"))
                self.assertTrue(bounded.endswith("-TAIL"))
                self.assertIn("renderer output truncated", bounded)
                self.assertIn(bounded, detail)
        boundary = "a" * (8 * 1024)
        self.assertEqual(boundary, self.renderer.bounded_output(boundary))

    def test_empty_failure_output_still_reports_failure_state(self):
        ok, detail = self.render_stub()
        self.assertFalse(ok)
        self.assertIn("exit code: 1; output SVG: missing", detail)
        self.assertIn("stderr:\n<empty>\nstdout:\n<empty>", detail)

    def test_missing_svg_with_zero_exit_is_failure(self):
        ok, detail = self.render_stub(returncode=0)
        self.assertFalse(ok)
        self.assertIn("exit code: 0; output SVG: missing", detail)

    def test_nonzero_exit_with_svg_is_failure(self):
        ok, detail = self.render_stub(returncode=7, output=True)
        self.assertFalse(ok)
        self.assertIn("exit code: 7; output SVG: present", detail)

    def test_success_requires_zero_exit_and_svg(self):
        self.assertEqual((True, ""), self.render_stub(returncode=0, output=True))

    def test_timeout_retains_bounded_partial_streams_and_fails_with_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "fixture.svg").write_text("<svg/>")
            partial = b"ROOT TIMEOUT CAUSE\n" + b"frame\n" * 5000 + b"END"
            error = subprocess.TimeoutExpired(
                ["fixture-npx"], self.renderer.RENDER_TIMEOUT,
                output=b"partial stdout", stderr=partial,
            )
            with mock.patch.object(self.renderer.subprocess, "run", side_effect=error):
                ok, detail = self.renderer.render("fixture-npx", "graph TD\nA-->B", workdir, "fixture")
        self.assertFalse(ok)
        self.assertIn("renderer timed out after 300s; exit code: unavailable; output SVG: present", detail)
        self.assertIn("ROOT TIMEOUT CAUSE", detail)
        self.assertIn("END", detail)
        self.assertIn("stdout:\npartial stdout", detail)
        self.assertLessEqual(len(self.renderer.bounded_output(partial).encode("utf-8")), 8 * 1024)

    def test_spawn_error_still_fails(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(self.renderer.subprocess, "run", side_effect=OSError("fixture unavailable")),
        ):
            ok, detail = self.renderer.render("fixture-npx", "graph TD\nA-->B", Path(tmp), "fixture")
        self.assertFalse(ok)
        self.assertIn("renderer failed to run; exit code: unavailable; output SVG: missing", detail)
        self.assertIn("error:\nfixture unavailable", detail)


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
            'uvx --from "ruff==${RUFF_VERSION}" ruff check .',
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
