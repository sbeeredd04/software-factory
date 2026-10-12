"""Tests for the install.py transaction engine.

Encodes the VAL-INSTALL transaction assertions (dry-run purity, exact write
set plus ownership manifest, volatile-only .gitignore entries, HOME
untouched, second-install byte-level no-op, conflict handling with zero
writes, backup permissions, settings merge preservation, managed-block
rules, symlink/malformed refusals, no Git mutation) and the installer's
VAL-CONTEXT obligations (the committed context home is never written,
listed or ignored).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

MANIFEST = ".software-factory/installation.json"
GITIGNORE_LINES = (
    ".software-factory/runtime/",
    ".software-factory/backups/",
    ".software-factory/runs/",
    ".software-factory/active.json",
    ".software-factory/state.lock",
    ".software-factory/installation.json",
)
CONTEXT_FILES = {
    ".software-factory/context/principles/product.md": "product principles\n",
    ".software-factory/context/CODEBASE.md": "# map\n",
    ".software-factory/context/board/roadmap.json": "{}\n",
    ".software-factory/context/decisions/0001-demo.md": "# decision\n",
}


class InstallerCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-install-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.env, self.records, self.guard_log = support.recorder_env()
        self.home, self.home_snapshot = support.home_sentinel(self.temp)
        self.env["HOME"] = str(self.home)

    def install(self, repo, *args):
        return support.run_installer(
            "install", "--project", repo, *args, env=self.env
        )

    def assert_recorders_empty(self):
        self.assertEqual([], list(self.records.iterdir()))
        self.assertFalse(
            self.guard_log.exists() and self.guard_log.read_text().strip(),
            "host CLIs must never be invoked",
        )

    def assert_home_untouched(self, before):
        self.assertEqual(before, self.home_snapshot())


class DryRunTests(InstallerCase):
    def test_dry_run_writes_nothing_and_spawns_nothing(self):
        repo = support.fresh_repo(self.temp)
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "all", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(".claude/skills", result.stdout)  # a printed plan
        self.assertIn("dry-run", result.stdout.lower())
        self.assertEqual(before, support.tree_hashes(repo))
        for absent in (".claude", ".cursor", ".codex", ".agents",
                       ".software-factory", "_bmad"):
            self.assertFalse((repo / absent).exists(), absent)
        self.assert_recorders_empty()
        status = support.Workspace.git(repo, "status", "--porcelain")
        self.assertEqual("", status.stdout.strip())

    def test_dry_run_with_existing_project_writes_nothing(self):
        repo = support.existing_repo(self.temp)
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "claude-code", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assert_recorders_empty()


class FreshInstallTests(InstallerCase):
    def test_writes_exactly_the_owned_plan_with_manifest(self):
        repo = support.fresh_repo(self.temp)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_recorders_empty()

        manifest_path = repo / MANIFEST
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(1, manifest["version"])
        self.assertEqual(["claude-code"], manifest["hosts"])
        self.assertEqual("full", manifest["profile"])
        listed = {entry["path"] for entry in manifest["files"]}
        for entry in manifest["files"]:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            current = support.tree_hashes(repo)[entry["path"]]
            self.assertEqual(
                entry["sha256"], current, f"manifest hash matches {entry['path']}"
            )

        # Every created/modified path is listed; nothing unlisted was written.
        # (The manifest itself and the transient install lock are not owned
        # payloads - the manifest cannot hash itself.)
        created = set(support.tree_hashes(repo)) - {"README.md", MANIFEST}
        self.assertEqual(created, listed)

        # Install never creates runtime state pointers.
        self.assertFalse((repo / ".software-factory/active.json").exists())
        self.assertFalse((repo / ".software-factory/state.lock").exists())

    def test_aborted_run_writes_no_manifest(self):
        repo = support.fresh_repo(self.temp)
        collision = repo / ".claude/skills/sf-patterns/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("foreign content\n")
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, result.returncode)
        self.assertFalse((repo / MANIFEST).exists())

    def test_skills_only_profile_writes_skills_and_no_hooks(self):
        repo = support.fresh_repo(self.temp)
        result = self.install(
            repo, "--host", "claude-code", "--profile", "skills-only"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((repo / ".claude/skills/sf-patterns/SKILL.md").is_file())
        self.assertFalse((repo / ".claude/agents").exists())
        self.assertFalse((repo / ".claude/settings.json").exists())
        self.assertFalse((repo / "CLAUDE.md").exists())
        self.assertFalse((repo / ".software-factory/runtime").exists())
        manifest = json.loads((repo / MANIFEST).read_text())
        self.assertEqual("skills-only", manifest["profile"])


class GitignoreTests(InstallerCase):
    def test_volatile_entries_only_and_user_lines_survive(self):
        repo = support.existing_repo(self.temp)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        text = (repo / ".gitignore").read_text()
        self.assertIn("build/\n", text)
        self.assertIn(".env\n", text)
        for entry in GITIGNORE_LINES:
            self.assertIn(entry, text.splitlines())
        self.assertNotIn(".software-factory/", text.splitlines())
        self.assertNotIn(".software-factory/context/", text)

        def ignored(rel):
            probe = subprocess.run(
                ["git", "-C", str(repo), "check-ignore", "-q", "--", rel],
                capture_output=True,
                check=False,
            )
            return probe.returncode == 0

        for volatile in (
            ".software-factory/active.json",
            ".software-factory/state.lock",
            ".software-factory/runtime/hook.py",
            ".software-factory/backups/x",
            ".software-factory/runs/demo/run.json",
            ".software-factory/installation.json",
        ):
            self.assertTrue(ignored(volatile), volatile)
        for trackable in (
            ".software-factory/config.yaml",
            ".software-factory/context/",
            ".software-factory/context/principles/product.md",
            ".software-factory/context/CODEBASE.md",
            ".software-factory/context/board/roadmap.json",
            ".software-factory/context/board/dashboard.html",
            ".software-factory/context/decisions/",
            ".software-factory/overlays/z.md",
        ):
            self.assertFalse(ignored(trackable), trackable)


class HomeUntouchedTests(InstallerCase):
    def test_home_host_configs_never_touched(self):
        repo = support.existing_repo(self.temp)
        before = self.home_snapshot()
        result = self.install(repo, "--host", "all")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_home_untouched(before)
        again = self.install(repo, "--host", "all", "--dry-run")
        self.assertEqual(0, again.returncode, again.stderr)
        self.assert_home_untouched(before)


class IdempotencyTests(InstallerCase):
    def test_second_install_is_a_byte_level_noop(self):
        repo = support.fresh_repo(self.temp)
        first = self.install(repo, "--host", "all")
        self.assertEqual(0, first.returncode, first.stderr)
        before = support.tree_hashes(repo)
        manifest_bytes = (repo / MANIFEST).read_bytes()
        second = self.install(repo, "--host", "all")
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn("0 changes", second.stdout)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertEqual(manifest_bytes, (repo / MANIFEST).read_bytes())

        backups = repo / ".software-factory/backups"
        self.assertFalse(backups.exists() and any(backups.iterdir()))

        settings = json.loads((repo / ".claude/settings.json").read_text())
        owned = [
            handler["command"]
            for event in ("SessionStart", "PreCompact")
            for group in settings["hooks"][event]
            for handler in group["hooks"]
            if "runtime/hook.py" in handler.get("command", "")
        ]
        self.assertEqual(2, len(owned))  # exactly one per event


class ConflictTests(InstallerCase):
    def test_unowned_collision_aborts_with_zero_writes(self):
        repo = support.fresh_repo(self.temp)
        collision = repo / ".claude/skills/sf-patterns/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("foreign content\n")
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, result.returncode)
        self.assertIn(".claude/skills/sf-patterns/SKILL.md", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertFalse((repo / MANIFEST).exists())
        self.assert_recorders_empty()

    def test_modified_managed_file_conflicts_then_allow_overwrite_backs_up(self):
        repo = support.fresh_repo(self.temp)
        first = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, first.returncode, first.stderr)
        target = repo / ".claude/agents/sf-engineer.md"
        target.write_text(target.read_text() + "# sentinel-user-edit\n")
        modified_hash = support.tree_hashes(repo)[".claude/agents/sf-engineer.md"]
        before = support.tree_hashes(repo)

        conflict = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, conflict.returncode)
        self.assertIn(".claude/agents/sf-engineer.md", conflict.stderr)
        self.assertEqual(before, support.tree_hashes(repo))

        allowed = self.install(
            repo,
            "--host",
            "claude-code",
            "--allow-overwrite",
            ".claude/agents/sf-engineer.md",
        )
        self.assertEqual(0, allowed.returncode, allowed.stderr)
        self.assertNotIn("sentinel-user-edit", allowed.stdout)

        backups = repo / ".software-factory/backups"
        installs = [p for p in backups.iterdir() if p.is_dir()]
        self.assertEqual(1, len(installs))
        backup = installs[0] / ".claude/agents/sf-engineer.md"
        self.assertTrue(backup.is_file())
        backup_hash = support.tree_hashes(backups)[
            f"{installs[0].name}/.claude/agents/sf-engineer.md"
        ]
        self.assertEqual(modified_hash, backup_hash)
        dir_mode = stat.S_IMODE(installs[0].stat().st_mode)
        file_mode = stat.S_IMODE(backup.stat().st_mode)
        self.assertEqual(0o700, dir_mode)
        self.assertEqual(0o600, file_mode)

        # The projection is restored to the canonical bytes.
        canonical = (support.REPO / "agents/sf-engineer.md").read_bytes()
        self.assertEqual(canonical, target.read_bytes())

    def test_allow_overwrite_without_conflict_is_an_error(self):
        repo = support.fresh_repo(self.temp)
        result = self.install(
            repo, "--host", "claude-code",
            "--allow-overwrite", ".claude/agents/sf-engineer.md",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("--allow-overwrite", result.stderr)


class SettingsMergeTests(InstallerCase):
    def test_merge_preserves_user_keys_hooks_and_permissions(self):
        repo = support.existing_repo(self.temp)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads((repo / ".claude/settings.json").read_text())
        self.assertEqual("opus", settings["model"])
        self.assertEqual({"TEAM_CITY": "1"}, settings["env"])
        self.assertEqual(
            {"allow": ["Bash(npm test:*)"]}, settings["permissions"]
        )
        expected_pre = json.loads(support.CLAUDE_SETTINGS_FIXTURE)["hooks"]["PreToolUse"]
        self.assertEqual(expected_pre, settings["hooks"]["PreToolUse"])
        self.assertNotIn("bypassPermissions", json.dumps(settings))
        self.assertNotIn("defaultMode", json.dumps(settings))
        for event, matcher in (
            ("SessionStart", "startup|resume|clear|compact"),
            ("PreCompact", "manual|auto"),
        ):
            owned = [
                group
                for group in settings["hooks"][event]
                if any(
                    "runtime/hook.py" in handler.get("command", "")
                    for handler in group["hooks"]
                )
            ]
            self.assertEqual(1, len(owned), event)
            self.assertEqual(matcher, owned[0]["matcher"])

        # A second install adds no duplicate owned entries.
        again = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, again.returncode, again.stderr)
        settings = json.loads((repo / ".claude/settings.json").read_text())
        self.assertEqual(1, len(settings["hooks"]["SessionStart"]))
        self.assertEqual(1, len(settings["hooks"]["PreCompact"]))

    def test_user_session_start_hook_survives_merge(self):
        repo = support.existing_repo(self.temp)
        settings_path = repo / ".claude/settings.json"
        settings = json.loads(settings_path.read_text())
        settings["hooks"]["SessionStart"] = [
            {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hi"}]}
        ]
        settings_path.write_text(json.dumps(settings))
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        merged = json.loads(settings_path.read_text())["hooks"]["SessionStart"]
        commands = [h["command"] for g in merged for h in g["hooks"]]
        self.assertIn("echo hi", commands)
        self.assertEqual(
            1, len([c for c in commands if "runtime/hook.py" in c])
        )


class ManagedBlockTests(InstallerCase):
    def test_block_markers_unique_and_user_text_preserved(self):
        repo = support.existing_repo(self.temp)
        original = (repo / "CLAUDE.md").read_bytes()
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        content = (repo / "CLAUDE.md").read_text()
        begin = "<!-- software-factory:begin -->"
        end = "<!-- software-factory:end -->"
        self.assertEqual(1, content.count(begin))
        self.assertEqual(1, content.count(end))
        lines = content.splitlines(keepends=True)
        kept = []
        inside = False
        for line in lines:
            if line.strip() == begin:
                inside = True
                continue
            if line.strip() == end:
                inside = False
                continue
            if not inside:
                kept.append(line)
        self.assertEqual(original.decode(), "".join(kept))

    def test_tampered_markers_are_a_conflict_never_a_rewrite(self):
        repo = support.existing_repo(self.temp)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        claude_md = repo / "CLAUDE.md"
        tampered = "\n".join(
            line
            for line in claude_md.read_text().splitlines()
            if line.strip() != "<!-- software-factory:end -->"
        )
        claude_md.write_text(tampered + "\n")
        snapshot = claude_md.read_bytes()
        conflict = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, conflict.returncode)
        self.assertIn("managed block", conflict.stderr)
        self.assertIn("CLAUDE.md", conflict.stderr)
        self.assertEqual(snapshot, claude_md.read_bytes())
        self.assertEqual(
            1, claude_md.read_text().count("<!-- software-factory:begin -->")
        )


class RefusalTests(InstallerCase):
    def test_symlink_escape_refused_without_writes(self):
        repo = support.fresh_repo(self.temp)
        outside = self.temp / "outside"
        outside.mkdir()
        (repo / ".claude").mkdir()
        (repo / ".claude/skills").symlink_to(outside)
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, result.returncode)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertEqual([], list(outside.iterdir()))
        self.assertFalse((repo / MANIFEST).exists())

    def test_malformed_settings_refused_without_writes(self):
        repo = support.fresh_repo(self.temp)
        settings = repo / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model": "opus"')
        before = support.tree_hashes(repo)
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(1, result.returncode)
        self.assertIn("settings.json", result.stderr)
        self.assertEqual(before, support.tree_hashes(repo))
        self.assertEqual('{"model": "opus"', settings.read_text())
        self.assertFalse((repo / MANIFEST).exists())


class GitUntouchedTests(InstallerCase):
    def test_install_never_mutates_git(self):
        repo = support.existing_repo(self.temp)
        head = support.Workspace.git(repo, "rev-parse", "HEAD").stdout
        log_count = support.Workspace.git(repo, "log", "--oneline").stdout
        notes = (repo / "notes.txt").read_bytes()
        scratch = (repo / "scratch.txt").read_bytes()
        result = self.install(repo, "--host", "all")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(head, support.Workspace.git(repo, "rev-parse", "HEAD").stdout)
        self.assertEqual(
            log_count, support.Workspace.git(repo, "log", "--oneline").stdout
        )
        self.assertEqual(
            "", support.Workspace.git(repo, "stash", "list").stdout.strip()
        )
        self.assertEqual(notes, (repo / "notes.txt").read_bytes())
        self.assertEqual(scratch, (repo / "scratch.txt").read_bytes())
        status = support.Workspace.git(repo, "status", "--porcelain").stdout
        changed = {line[3:] for line in status.splitlines()}
        factory_prefixes = (
            ".gitignore",
            "CLAUDE.md",
            ".claude/",
            ".cursor/",  # pre-existing user hook config in this fixture
            ".software-factory/",
        )
        for entry in changed - {"notes.txt", "scratch.txt"}:
            self.assertTrue(
                entry.startswith(factory_prefixes),
                f"unexpected git status entry: {entry}",
            )
        self.assertIn("notes.txt", changed)
        self.assertIn("scratch.txt", changed)


class ContextHomeTests(InstallerCase):
    def test_installer_never_touches_or_claims_the_context_home(self):
        repo = support.existing_repo(self.temp)
        for rel, content in CONTEXT_FILES.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        before = support.tree_hashes(repo / ".software-factory/context")
        result = self.install(repo, "--host", "claude-code")
        self.assertEqual(0, result.returncode, result.stderr)
        after = support.tree_hashes(repo / ".software-factory/context")
        self.assertEqual(before, after)
        prefix = ".software-factory/context/"
        self.assertEqual(
            {rel.removeprefix(prefix) for rel in CONTEXT_FILES}, set(after)
        )
        manifest = (repo / MANIFEST).read_text()
        self.assertNotIn(".software-factory/context", manifest)


if __name__ == "__main__":
    unittest.main()
