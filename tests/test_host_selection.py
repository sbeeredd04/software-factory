"""Tests for multi-host selection and combined installs.

Encodes VAL-INSTALL-013 (--host auto reports a choice or demands an explicit
host, never executes host binaries), VAL-INSTALL-014 (plugin and project
installs for the same host refuse to stack), VAL-HOST-013 (--host all writes
all three projections with one shared .agents/skills payload) and
VAL-INSTALL-018 (sequential per-host installs converge to the all tree).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

_spec = importlib.util.spec_from_file_location(
    "sf_validate", support.REPO / "scripts" / "validate.py"
)
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

MANIFEST = ".software-factory/installation.json"
EXPLICIT_ONLY = {
    "software-factory",
    "sf-help",
    "sf-agents",
    "sf-evolve",
    "sf-eval",
    "sf-principles",
}


def minimal_env(*stub_names):
    """A PATH containing only the given recording stubs (no host binaries
    unless named); the installer's own python3 needs no PATH entry because
    tests invoke it by absolute path and it falls back to sys.executable."""
    stub_dir = Path(tempfile.mkdtemp(prefix="sf-path-"))
    log = stub_dir / "guard.log"
    for name in stub_names:
        script = stub_dir / name
        script.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$0 $*" >> "$SF_GUARD_LOG"\nexit 127\n'
        )
        script.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(stub_dir)
    env["SF_GUARD_LOG"] = str(log)
    env.pop("CURSOR_VERSION", None)
    env.pop("CURSOR_PROJECT_DIR", None)
    return env, log


def projection_hashes(repo):
    """Tree hashes minus the manifest and backups (VAL-INSTALL-018 scope)."""
    return {
        rel: digest
        for rel, digest in support.tree_hashes(repo).items()
        if rel != MANIFEST and not rel.startswith(".software-factory/backups/")
    }


class SelectionCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-host-select-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.home, _ = support.home_sentinel(self.temp)

    def install(self, repo, *args, env):
        env.setdefault("HOME", str(self.home))
        return support.run_installer(
            "install", "--project", repo, *args, "--skip-bmad", env=env
        )


class AutoDetectTests(SelectionCase):
    def test_bare_repo_without_binaries_demands_explicit_host(self):
        repo = support.fresh_repo(self.temp)
        env, log = minimal_env()
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(1, result.returncode)
        self.assertIn("no host detected", result.stderr)
        self.assertIn("--host", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse(log.exists())

    def test_cursor_marker_only_selects_cursor(self):
        repo = support.fresh_repo(self.temp)
        cursor = repo / ".cursor"
        cursor.mkdir()
        (cursor / "hooks.json").write_text(support.CURSOR_HOOKS_FIXTURE)
        env, _ = minimal_env()  # no host binaries on PATH at all
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("cursor", result.stdout)
        self.assertTrue((repo / ".cursor/agents").is_dir())
        self.assertTrue((repo / ".agents/skills/software-factory").is_dir())
        self.assertFalse((repo / ".claude").exists())
        self.assertFalse((repo / ".codex").exists())

    def test_claude_marker_with_stubbed_binary_selects_without_executing(self):
        repo = support.fresh_repo(self.temp)
        settings = repo / ".claude/settings.json"
        settings.parent.mkdir()
        settings.write_text(support.CLAUDE_SETTINGS_FIXTURE)
        # Every host binary appears "available" via guard stubs; the single
        # project marker must decide, and selection must not execute one.
        env, guard_log, _stub_dir = support.guard_env()
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("claude-code", result.stdout)
        self.assertTrue((repo / ".claude/skills/software-factory").is_dir())
        self.assertFalse((repo / ".cursor").exists())
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())

    def test_ambiguous_markers_demand_explicit_host(self):
        repo = support.existing_repo(self.temp)  # .claude/ and .cursor/
        env, log = minimal_env()
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(1, result.returncode)
        self.assertIn("explicit", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse(log.exists())

    def test_multiple_binaries_without_markers_demand_explicit_host(self):
        repo = support.fresh_repo(self.temp)
        env, guard_log, _ = support.guard_env()  # all host CLIs stubbed
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(1, result.returncode)
        self.assertIn("--host", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())

    def test_single_binary_without_markers_selects_that_host(self):
        repo = support.fresh_repo(self.temp)
        env, log = minimal_env("codex")
        result = self.install(repo, "--host", "auto", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("codex", result.stdout)
        self.assertTrue((repo / ".codex/agents").is_dir())
        self.assertFalse((repo / ".claude").exists())
        self.assertFalse((repo / ".cursor").exists())
        # command -v style detection never executes the binary.
        self.assertFalse(log.exists())


class PluginStackingTests(SelectionCase):
    def test_claude_plugin_refuses_project_stacking_but_not_other_hosts(self):
        repo = support.fresh_repo(self.temp)
        settings = repo / ".claude/settings.json"
        settings.parent.mkdir()
        fixture = (
            '{"enabledPlugins":{"software-factory@software-factory":true}}'
        )
        settings.write_text(fixture)
        env, guard_log, _ = support.guard_env()
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "claude-code", env=env)
        self.assertEqual(1, result.returncode)
        self.assertIn("plugin", result.stderr)
        self.assertIn("migrat", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        # A different host is not a stacking conflict.
        other = self.install(repo, "--host", "cursor", env=env)
        self.assertEqual(0, other.returncode, other.stderr)
        self.assertTrue((repo / ".cursor/agents").is_dir())
        self.assertEqual(fixture, settings.read_text())
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())

    def test_codex_plugin_in_config_toml_refuses_stacking(self):
        repo = support.fresh_repo(self.temp)
        codex = repo / ".codex"
        codex.mkdir()
        config = codex / "config.toml"
        fixture = (
            '[plugins."software-factory@software-factory"]\nenabled = true\n'
        )
        config.write_text(fixture)
        env, _, _ = support.guard_env()
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "codex", env=env)
        self.assertEqual(1, result.returncode)
        self.assertIn("plugin", result.stderr)
        self.assertIn("migrat", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        other = self.install(repo, "--host", "claude-code", env=env)
        self.assertEqual(0, other.returncode, other.stderr)
        self.assertEqual(fixture, config.read_text())


class AllHostsTests(SelectionCase):
    def test_host_all_writes_three_projections_one_shared_payload(self):
        repo = support.fresh_repo(self.temp)
        env, guard_log, _ = support.guard_env()
        result = self.install(repo, "--host", "all", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((repo / ".claude/skills").is_dir())
        self.assertTrue((repo / ".cursor/agents").is_dir())
        self.assertTrue((repo / ".codex/agents").is_dir())
        # One shared payload: exactly eleven SKILL.md, each name once.
        skill_mds = sorted(
            path.relative_to(repo / ".agents/skills").as_posix()
            for path in (repo / ".agents/skills").rglob("SKILL.md")
        )
        self.assertEqual(
            [f"{name}/SKILL.md" for name in sorted(validate.SKILLS)], skill_mds
        )
        # No Claude-only keys anywhere in the shared payload.
        for path in (repo / ".agents/skills").rglob("*"):
            if path.is_file():
                raw = path.read_text()
                self.assertNotIn("argument-hint", raw, path)
                self.assertNotIn("disable-model-invocation", raw, path)
        # The Codex policy files ride along once.
        for skill in sorted(EXPLICIT_ONLY | {"sf-crawl"}):
            self.assertTrue(
                (repo / f".agents/skills/{skill}/agents/openai.yaml").is_file(),
                skill,
            )
        # One managed block per pointer file.
        for pointer in ("CLAUDE.md", "AGENTS.md"):
            content = (repo / pointer).read_text()
            self.assertEqual(
                1, content.count("<!-- software-factory:begin -->"), pointer
            )
        # A second all install is a byte-level no-op.
        before = support.tree_hashes(repo)
        again = self.install(repo, "--host", "all", env=env)
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("0 changes", again.stdout)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())


class ConvergenceTests(SelectionCase):
    def test_sequential_installs_converge_to_the_all_tree(self):
        # Same path for both runs so embedded absolute hook paths match:
        # sequential first, then the tree is rebuilt fresh for --host all.
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        for host in ("claude-code", "cursor", "codex"):
            result = self.install(repo, "--host", host, env=env)
            self.assertEqual(0, result.returncode, f"{host}: {result.stderr}")
        sequential = projection_hashes(repo)
        shutil.rmtree(repo)
        repo = support.fresh_repo(self.temp)
        result = self.install(repo, "--host", "all", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        combined = projection_hashes(repo)
        self.assertEqual(sorted(sequential), sorted(combined))
        self.assertEqual(sequential, combined)
        # The shared payload exists exactly once (no per-host duplication).
        count = sum(
            1 for rel in combined if rel.endswith("skills/software-factory/SKILL.md")
        )
        self.assertEqual(2, count)  # .claude/skills + shared .agents/skills


if __name__ == "__main__":
    unittest.main()
