"""Tests for multi-host selection and combined installs.

Encodes VAL-INSTALL-013 (--host auto reports a choice or demands an explicit
host, never executes host binaries), VAL-INSTALL-014 (plugin and project
installs for the same host refuse to stack), VAL-HOST-013 (--host all writes
all three projections with one shared .agents/skills payload) and
VAL-INSTALL-018 (sequential per-host installs converge to the all tree).
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class GitFixtureTests(unittest.TestCase):
    def test_git_wrapper_preserves_arguments_options_result_and_errors(self):
        repo = Path('fixture-repo')
        args = ('-c', 'user.name=Fixture', 'commit', '-q', '-m', 'fixture')
        expected = ['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0',
                    '-C', str(repo), *args]
        result = subprocess.CompletedProcess(expected, 0, stdout='fixture output\n')
        with mock.patch.object(support.subprocess, 'run', return_value=result) as run:
            self.assertIs(result, support.Workspace.git(repo, *args))
            run.assert_called_once_with(
                expected, check=True, capture_output=True, text=True,
            )
        error = subprocess.CalledProcessError(7, expected, stderr='fixture failure')
        with mock.patch.object(support.subprocess, 'run', side_effect=error) as run:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                support.Workspace.git(repo, *args)
            self.assertIs(error, caught.exception)
            run.assert_called_once_with(
                expected, check=True, capture_output=True, text=True,
            )

    def test_git_maintenance_controls_override_child_environment_without_persistence(self):
        parent_env = dict(os.environ)
        with tempfile.TemporaryDirectory(prefix='sf-git-control-') as temporary:
            repo = support.fresh_repo(temporary)
            config = repo / '.git/config'
            before = config.read_bytes()
            global_config = Path(temporary).resolve() / 'global.gitconfig'
            global_before = b'[maintenance]\n\tauto = true\n[gc]\n\tauto = 1\n'
            global_config.write_bytes(global_before)
            trace = Path(temporary).resolve() / 'git-trace.jsonl'
            child_env = dict(parent_env)
            child_env.pop('GIT_CONFIG_PARAMETERS', None)
            child_env.update(
                GIT_CONFIG_COUNT='2',
                GIT_CONFIG_KEY_0='maintenance.auto', GIT_CONFIG_VALUE_0='true',
                GIT_CONFIG_KEY_1='gc.auto', GIT_CONFIG_VALUE_1='1',
                GIT_CONFIG_GLOBAL=str(global_config), GIT_TRACE2_EVENT=str(trace),
                PYTHONPATH=str(Path(__file__).resolve().parent),
            )
            child = '''
import json
import os
import subprocess
import sys
from pathlib import Path
import support

before_env = dict(os.environ)
observed = {}
for key in ('maintenance.auto', 'gc.auto'):
    inherited = subprocess.run(
        ['git', '-C', sys.argv[1], 'config', '--get', key],
        check=True, capture_output=True, text=True,
    )
    controlled = support.Workspace.git(sys.argv[1], 'config', '--get', key)
    observed[key] = [inherited.stdout.strip(), controlled.stdout.strip()]
before_head = support.Workspace.git(sys.argv[1], 'rev-parse', 'HEAD').stdout.strip()
support.Workspace.git(
    sys.argv[1], '-c', 'user.name=' + support.FIXTURE_NAME,
    '-c', 'user.email=' + support.FIXTURE_EMAIL,
    'commit', '--allow-empty', '--no-gpg-sign', '-m', 'fixture maintenance check',
)
after_head = support.Workspace.git(sys.argv[1], 'rev-parse', 'HEAD').stdout.strip()
events = [json.loads(line) for line in Path(os.environ['GIT_TRACE2_EVENT']).read_text().splitlines()]
automatic_children = [event for event in events if event.get('event') == 'child_start'
                      and any(arg in ('maintenance', 'gc') or Path(arg).name in ('git-maintenance', 'git-gc')
                              for arg in event.get('argv', []))]
commit_events = [event for event in events if event.get('event') == 'start'
                 and 'commit' in event.get('argv', []) and '--allow-empty' in event['argv']]
print(json.dumps({'values': observed, 'head_changed': before_head != after_head,
                  'commit_events': len(commit_events), 'automatic_children': len(automatic_children),
                  'environment_unchanged': before_env == dict(os.environ)}))
'''
            result = subprocess.run(
                [sys.executable, '-c', child, str(repo)], cwd=temporary,
                env=child_env, check=True, capture_output=True, text=True,
            )
            self.assertEqual(
                {'values': {'maintenance.auto': ['true', 'false'], 'gc.auto': ['1', '0']},
                 'head_changed': True, 'commit_events': 1, 'automatic_children': 0,
                 'environment_unchanged': True},
                json.loads(result.stdout),
            )
            self.assertEqual(before, config.read_bytes())
            self.assertEqual(global_before, global_config.read_bytes())
        self.assertEqual(parent_env, dict(os.environ))


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
        # Cursor invocation policy accompanies Codex policy in one shared tree.
        for path in (repo / ".agents/skills").rglob("*"):
            if path.is_file():
                raw = path.read_text()
                self.assertNotIn("argument-hint", raw, path)
                if path.name == "SKILL.md":
                    meta = validate.parse_frontmatter(raw, path)
                    expected = "true" if path.parent.name in EXPLICIT_ONLY else None
                    self.assertEqual(expected, meta.get("disable-model-invocation"))
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
    def test_sequential_installs_keep_complete_ownership_and_reinstall_cleanly(self):
        env, guard_log, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        prior_paths = set()
        for index, host in enumerate(("claude-code", "cursor", "codex"), start=1):
            result = self.install(repo, "--host", host, env=env)
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = json.loads((repo / MANIFEST).read_text())
            self.assertEqual(
                ["claude-code", "cursor", "codex"][:index], manifest["hosts"]
            )
            owned = {entry["path"]: entry for entry in manifest["files"]}
            self.assertTrue(prior_paths <= owned.keys())
            hashes = support.tree_hashes(repo)
            for path, entry in owned.items():
                self.assertEqual(hashes[path], entry["sha256"], path)
            prior_paths = set(owned)
        before = support.tree_hashes(repo)
        for host in ("all", "claude-code", "cursor", "codex"):
            result = self.install(repo, "--host", host, env=env)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("0 changes", result.stdout)
            self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())

    def test_adding_host_keeps_modified_prior_file_hash_and_backup(self):
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        rel = ".claude/skills/sf-patterns/SKILL.md"
        target = repo / rel
        target.parent.mkdir(parents=True)
        target.write_text("original user content\n")
        first = self.install(
            repo, "--host", "claude-code", "--allow-overwrite", rel, env=env
        )
        self.assertEqual(0, first.returncode, first.stderr)
        prior = next(
            entry for entry in json.loads((repo / MANIFEST).read_text())["files"]
            if entry["path"] == rel
        )
        self.assertEqual("original user content\n", (repo / prior["backup"]).read_text())
        target.write_text("local modification after install\n")
        result = self.install(repo, "--host", "cursor", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        current = next(
            entry for entry in json.loads((repo / MANIFEST).read_text())["files"]
            if entry["path"] == rel
        )
        self.assertEqual(prior, current)
        self.assertEqual("local modification after install\n", target.read_text())
        before = support.tree_hashes(repo)
        refusal = self.install(repo, "--host", "claude-code", env=env)
        self.assertEqual(1, refusal.returncode)
        self.assertIn("modified locally", refusal.stderr)
        self.assertEqual(before, support.tree_hashes(repo))

    def test_skills_only_addition_preserves_full_profile_and_prior_ownership(self):
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        result = self.install(repo, "--host", "claude-code", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        prior = json.loads((repo / MANIFEST).read_text())
        result = self.install(
            repo, "--host", "cursor", "--profile", "skills-only", env=env
        )
        self.assertEqual(0, result.returncode, result.stderr)
        current = json.loads((repo / MANIFEST).read_text())
        self.assertEqual("full", current["profile"])
        self.assertEqual(["claude-code", "cursor"], current["hosts"])
        owned = {entry["path"]: entry for entry in current["files"]}
        for entry in prior["files"]:
            self.assertEqual(entry, owned[entry["path"]])
        self.assertFalse((repo / ".cursor/agents").exists())
        before = support.tree_hashes(repo)
        again = self.install(
            repo, "--host", "cursor", "--profile", "skills-only", env=env
        )
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(before, support.tree_hashes(repo))

    def test_shared_skills_host_addition_changes_only_cursor_invocation_fields(self):
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        first = self.install(
            repo, "--host", "codex", "--profile", "skills-only", env=env
        )
        self.assertEqual(0, first.returncode, first.stderr)
        before = projection_hashes(repo)
        addition = self.install(
            repo, "--host", "cursor", "--profile", "skills-only", env=env
        )
        self.assertEqual(0, addition.returncode, addition.stderr)
        after = projection_hashes(repo)
        changed = {rel for rel in before if before[rel] != after[rel]}
        self.assertEqual(
            {f".agents/skills/{skill}/SKILL.md" for skill in EXPLICIT_ONLY}, changed
        )
        self.assertIn("combined live host loading are unverified", addition.stdout)
        manifest = json.loads((repo / MANIFEST).read_text())
        self.assertEqual(["cursor", "codex"], manifest["hosts"])
        self.assertEqual("skills-only", manifest["profile"])
        snapshot = support.tree_hashes(repo)
        again = self.install(
            repo, "--host", "cursor", "--profile", "skills-only", env=env
        )
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(snapshot, support.tree_hashes(repo))

    def test_all_host_orders_and_profiles_converge_with_semantic_ownership(self):
        # Reuse a path so generated hook commands have the same project root.
        env, guard_log, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        hosts = ("claude-code", "cursor", "codex")
        for profile in ("full", "skills-only"):
            shutil.rmtree(repo)
            repo = support.fresh_repo(self.temp)
            result = self.install(repo, "--host", "all", "--profile", profile, env=env)
            self.assertEqual(0, result.returncode, result.stderr)
            combined = projection_hashes(repo)
            manifest = json.loads((repo / MANIFEST).read_text())
            expected_ownership = self.semantic_ownership(manifest)
            for order in itertools.permutations(hosts):
                with self.subTest(profile=profile, order=order):
                    shutil.rmtree(repo)
                    repo = support.fresh_repo(self.temp)
                    for host in order:
                        result = self.install(
                            repo, "--host", host, "--profile", profile, env=env
                        )
                        self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(combined, projection_hashes(repo))
                    actual = json.loads((repo / MANIFEST).read_text())
                    self.assertEqual(expected_ownership, self.semantic_ownership(actual))
                    # Backups describe actual history, unlike current ownership:
                    # adding Cursor after Codex backs up the unextended skill bytes.
                    for entry in actual["files"]:
                        if entry["backup"]:
                            self.assertTrue((repo / entry["backup"]).is_file())
                    snapshot = support.tree_hashes(repo)
                    for host in ("all", *hosts):
                        result = self.install(
                            repo, "--host", host, "--profile", profile, env=env
                        )
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertIn("0 changes", result.stdout)
                        self.assertEqual(snapshot, support.tree_hashes(repo))
        self.assertFalse(guard_log.exists() and guard_log.read_text().strip())

    @staticmethod
    def semantic_ownership(manifest):
        return {
            "pack": manifest["pack"], "version": manifest["version"],
            "hosts": manifest["hosts"], "profile": manifest["profile"],
            "files": [
                {key: value for key, value in entry.items() if key != "backup"}
                for entry in manifest["files"]
            ],
        }

    def test_shared_host_additions_preserve_mixed_profile_scope(self):
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        orders = (("cursor", "codex"), ("codex", "cursor"))
        profiles = (("full", "skills-only"), ("skills-only", "full"))
        for (first, second), (first_profile, second_profile) in itertools.product(orders, profiles):
            with self.subTest(first=first, first_profile=first_profile):
                shutil.rmtree(repo)
                repo = support.fresh_repo(self.temp)
                for host, profile in ((first, first_profile), (second, second_profile)):
                    result = self.install(
                        repo, "--host", host, "--profile", profile, env=env
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                manifest = json.loads((repo / MANIFEST).read_text())
                self.assertEqual("full", manifest["profile"])
                full_host = first if first_profile == "full" else second
                skills_host = second if first_profile == "full" else first
                self.assertTrue((repo / f".{full_host}/agents").is_dir())
                self.assertFalse((repo / f".{skills_host}/agents").exists())
                self.assertFalse((repo / f".{skills_host}/hooks.json").exists())
                snapshot = support.tree_hashes(repo)
                for host, profile in ((first, first_profile), (second, second_profile)):
                    result = self.install(
                        repo, "--host", host, "--profile", profile, env=env
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(snapshot, support.tree_hashes(repo))

    def test_shared_policy_transition_retains_backups_and_rejects_local_edits(self):
        env, _, _ = support.guard_env()
        repo = support.fresh_repo(self.temp)
        first = self.install(repo, "--host", "codex", "--profile", "skills-only", env=env)
        self.assertEqual(0, first.returncode, first.stderr)
        rel = ".agents/skills/software-factory/SKILL.md"
        target = repo / rel
        original = target.read_bytes()
        target.write_text("local skill edit\n")
        before = support.tree_hashes(repo)
        refused = self.install(repo, "--host", "cursor", env=env)
        self.assertEqual(1, refused.returncode)
        self.assertIn("modified locally", refused.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        target.write_bytes(original)
        result = self.install(repo, "--host", "cursor", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        manifest = json.loads((repo / MANIFEST).read_text())
        entry = next(item for item in manifest["files"] if item["path"] == rel)
        self.assertEqual(original, (repo / entry["backup"]).read_bytes())
        snapshot = support.tree_hashes(repo)
        result = self.install(repo, "--host", "codex", "--profile", "skills-only", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(snapshot, support.tree_hashes(repo))


if __name__ == "__main__":
    unittest.main()
