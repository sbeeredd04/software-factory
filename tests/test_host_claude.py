"""Tests for the Claude Code host projection.

Encodes VAL-HOST-001..004: the exact projected file set (skills mirrored
one-to-one, the eleven role agents, settings hooks, one CLAUDE.md managed
block, the runtime helper set), agent frontmatter rules (model inherit, no
isolation, no permission bypass), Claude-only frontmatter added by the
projection (argument-hint on every skill, disable-model-invocation on the
explicit-only set) with bodies byte-identical to canonical, and hook
entries with correct matchers, quoted command form, merged stderr (2>&1)
and no interpolated request text or secrets.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
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

_spec = importlib.util.spec_from_file_location(
    "sf_validate", support.REPO / "scripts" / "validate.py"
)
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

EXPLICIT_ONLY = {
    "software-factory",
    "sf-help",
    "sf-agents",
    "sf-evolve",
    "sf-eval",
    "sf-principles",
}
CC_START = (
    '{"session_id":"s1","cwd":"/fixture","hook_event_name":"SessionStart",'
    '"permission_mode":"default"}'
)
SECRET_RE = re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9-]{16,}|AKIA[0-9A-Z]{16}")


def canonical_tree():
    """Repo-relative files under skills/, excluding bytecode caches."""
    files = set()
    for path in sorted((support.REPO / "skills").rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files.add(path.relative_to(support.REPO / "skills").as_posix())
    return files


def frontmatter_of(path):
    text = Path(path).read_text(encoding="utf-8")
    raw_lines, body = validate.split_frontmatter(text, Path(path))
    return raw_lines, body


class ClaudeInstallCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-host-claude-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.env, self.records, self.guard_log = support.recorder_env()
        self.home, _ = support.home_sentinel(self.temp)
        self.env["HOME"] = str(self.home)
        self.env.pop("CURSOR_VERSION", None)
        self.env.pop("CURSOR_PROJECT_DIR", None)
        self.repo = support.existing_repo(self.temp)
        result = support.run_installer(
            "install", "--project", self.repo, "--host", "claude-code",
            "--skip-bmad", env=self.env,
        )
        assert result.returncode == 0, result.stderr

    def hook_command(self, event):
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        for group in settings["hooks"][event]:
            for handler in group["hooks"]:
                command = handler.get("command", "")
                if "runtime/hook.py" in command:
                    return command
        raise AssertionError(f"no owned hook command for {event}")


class FileSetTests(ClaudeInstallCase):
    def test_skills_tree_mirrors_canonical_one_to_one(self):
        projected = set()
        skills_dir = self.repo / ".claude/skills"
        for path in sorted(skills_dir.rglob("*")):
            if path.is_file():
                projected.add(path.relative_to(skills_dir).as_posix())
        self.assertEqual(canonical_tree(), projected)

    def test_exact_agent_set(self):
        agents = sorted(p.name for p in (self.repo / ".claude/agents").glob("*.md"))
        self.assertEqual(
            [f"{name}.md" for name in sorted(validate.AGENTS)], agents
        )

    def test_nothing_else_under_claude(self):
        allowed_prefixes = ("skills/", "agents/")
        for path in sorted((self.repo / ".claude").rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.repo / ".claude").as_posix()
            if rel == "settings.json":
                continue
            self.assertTrue(
                rel.startswith(allowed_prefixes), f"unexpected .claude file: {rel}"
            )

    def test_runtime_helper_set_and_pointer_block(self):
        runtime = self.repo / ".software-factory/runtime"
        names = sorted(p.name for p in runtime.glob("*.py"))
        self.assertEqual(["config.py", "gate.py", "hook.py", "state.py"], names)
        for name in names:
            canonical = support.SCRIPTS / name
            self.assertEqual(canonical.read_bytes(), (runtime / name).read_bytes())
        content = (self.repo / "CLAUDE.md").read_text()
        self.assertEqual(1, content.count("<!-- software-factory:begin -->"))
        self.assertEqual(1, content.count("<!-- software-factory:end -->"))
        # Claude-only projection: no other host artifacts are written.
        for absent in (".codex", ".agents", "AGENTS.md.factory"):
            self.assertFalse((self.repo / absent).exists(), absent)
        self.assertEqual(
            support.CURSOR_HOOKS_FIXTURE,
            (self.repo / ".cursor/hooks.json").read_text(),
        )


class SkillFrontmatterTests(ClaudeInstallCase):
    def test_claude_only_fields_added_only_by_projection(self):
        for skill in sorted(validate.SKILLS):
            with self.subTest(skill=skill):
                canonical_raw, _ = frontmatter_of(
                    support.REPO / "skills" / skill / "SKILL.md"
                )
                self.assertFalse(
                    any("argument-hint" in line for line in canonical_raw)
                )
                self.assertFalse(
                    any("disable-model-invocation" in line for line in canonical_raw)
                )
                projected_raw, _ = frontmatter_of(
                    self.repo / ".claude/skills" / skill / "SKILL.md"
                )
                hint = [line for line in projected_raw if line.startswith("argument-hint:")]
                self.assertEqual(1, len(hint), "every projected skill gets a hint")
                disabled = [
                    line
                    for line in projected_raw
                    if line.startswith("disable-model-invocation:")
                ]
                if skill in EXPLICIT_ONLY:
                    self.assertEqual(["disable-model-invocation: true"], disabled)
                else:
                    self.assertEqual([], disabled)

    def test_skill_bodies_are_byte_identical(self):
        for skill in sorted(validate.SKILLS):
            with self.subTest(skill=skill):
                _, canonical_body = frontmatter_of(
                    support.REPO / "skills" / skill / "SKILL.md"
                )
                _, projected_body = frontmatter_of(
                    self.repo / ".claude/skills" / skill / "SKILL.md"
                )
                self.assertEqual(canonical_body, projected_body)

    def test_non_skill_files_are_byte_identical(self):
        for rel in sorted(canonical_tree()):
            if rel.endswith("SKILL.md"):
                continue
            canonical = support.REPO / "skills" / rel
            projected = self.repo / ".claude/skills" / rel
            self.assertEqual(
                canonical.read_bytes(), projected.read_bytes(), rel
            )

    def test_projected_frontmatter_still_parses_cleanly(self):
        for skill in sorted(validate.SKILLS):
            with self.subTest(skill=skill):
                path = self.repo / ".claude/skills" / skill / "SKILL.md"
                meta = validate.parse_frontmatter(path.read_text(), path)
                self.assertEqual(skill, meta["name"])
                self.assertIsInstance(meta["description"], str)


class AgentFrontmatterTests(ClaudeInstallCase):
    def test_agents_model_inherit_no_isolation_no_bypass(self):
        for path in sorted((self.repo / ".claude/agents").glob("sf-*.md")):
            with self.subTest(agent=path.name):
                meta = validate.parse_frontmatter(path.read_text(), path)
                self.assertEqual(path.stem, meta["name"])
                self.assertIsInstance(meta["description"], str)
                self.assertTrue(meta["description"].strip())
                self.assertEqual("inherit", meta["model"])
                self.assertNotIn("isolation", meta)
                raw = path.read_text()
                self.assertNotIn("bypassPermissions", raw)
                self.assertNotRegex(raw, r"permissionMode:\s*(dontAsk|auto)")


class HookEntryTests(ClaudeInstallCase):
    def test_matchers_cover_every_source(self):
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        start = self.hook_command("SessionStart")
        self.assertIn("--event session-start", start)
        pre = self.hook_command("PreCompact")
        self.assertIn("--event pre-compact", pre)
        groups = {
            event: [
                group
                for group in settings["hooks"][event]
                if any("runtime/hook.py" in h.get("command", "") for h in group["hooks"])
            ]
            for event in ("SessionStart", "PreCompact")
        }
        start_matcher = groups["SessionStart"][0]["matcher"]
        for source in ("startup", "resume", "clear", "compact"):
            self.assertRegex(source, start_matcher)
        pre_matcher = groups["PreCompact"][0]["matcher"]
        for trigger in ("manual", "auto"):
            self.assertRegex(trigger, pre_matcher)

    def test_command_form_is_quoted_and_clean(self):
        for event in ("SessionStart", "PreCompact"):
            with self.subTest(event=event):
                command = self.hook_command(event)
                self.assertIn("python3", command)
                self.assertIn(".software-factory/runtime/hook.py", command)
                self.assertIn("--host claude-code", command)
                self.assertNotIn("$ARGUMENTS", command)
                self.assertNotIn("${CLAUDE_", command)
                self.assertIsNone(SECRET_RE.search(command))
                # stderr is merged into stdout so the sanitized recovery
                # warning is observable on stdout (VAL-HOST-018).
                self.assertTrue(command.rstrip().endswith("2>&1"))
                # Both the interpreter and the script path are quoted.
                parts = shlex.split(command.rstrip().removesuffix("2>&1"))
                self.assertTrue(parts[0].endswith("python3"))
                self.assertTrue(parts[1].endswith(".software-factory/runtime/hook.py"))

    def test_command_executes_verbatim_on_a_spaced_path(self):
        spaced = self.temp / "sf repo"
        repo = support.fresh_repo(spaced.parent, spaced.name)
        result = support.run_installer(
            "install", "--project", repo, "--host", "claude-code",
            "--skip-bmad", env=self.env,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads((repo / ".claude/settings.json").read_text())
        command = next(
            handler["command"]
            for group in settings["hooks"]["SessionStart"]
            for handler in group["hooks"]
            if "runtime/hook.py" in handler.get("command", "")
        )
        ran = subprocess.run(
            ["sh", "-c", command],
            input=CC_START,
            capture_output=True,
            text=True,
            cwd=repo,
            env=self.env,
            check=False,
        )
        self.assertEqual(0, ran.returncode, ran.stderr)
        self.assertEqual("", ran.stdout)  # inert without an active pointer

    def test_installed_hook_envelope_and_sanitized_warning(self):
        # Activate a program through the projected runtime helper itself.
        (self.repo / "principles.md").write_text("Authoritative principles\n")
        (self.repo / "tracker.yaml").write_text("stories: {}\n")
        state = self.repo / ".software-factory/runtime/state.py"
        init = subprocess.run(
            [sys.executable, str(state),
             "init", "--workspace", str(self.repo), "--program", "demo",
             "--tracker", "tracker.yaml", "--principles", "principles.md"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(0, init.returncode, init.stderr)
        command = self.hook_command("SessionStart")
        ran = subprocess.run(
            ["sh", "-c", command],
            input=CC_START,
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self.env,
            check=False,
        )
        self.assertEqual(0, ran.returncode, ran.stderr)
        envelope = json.loads(ran.stdout)
        context = envelope["hookSpecificOutput"]["additionalContext"]
        self.assertIn("not a new authorization", context)
        self.assertIn(".software-factory/runs/demo/CHECKPOINT.md", context)

        # Corrupt the pointer: the merged (2>&1) stream carries the sanitized
        # warning on stdout without echoing the payload or a traceback.
        (self.repo / ".software-factory/active.json").write_text('{"broken": tru')
        ran = subprocess.run(
            ["sh", "-c", command],
            input=CC_START,
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self.env,
            check=False,
        )
        self.assertEqual(0, ran.returncode)
        self.assertIn("recovery", ran.stdout)
        self.assertNotIn("broken", ran.stdout)
        self.assertNotIn("Traceback", ran.stdout)


if __name__ == "__main__":
    unittest.main()
