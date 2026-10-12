"""Shared fixtures and loaders for the kernel-helper tests.

Standard library only, matching the shipped helpers. Tests load the helpers
straight from the canonical skill scripts directory so the suite never depends
on sys.path tricks or an installed projection.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills" / "software-factory" / "scripts"
FIXTURE_EMAIL = "kernel-fixture@example.test"
FIXTURE_NAME = "Kernel Fixture"

_MODULES: dict[str, object] = {}
POINTER = ".software-factory/active.json"


def helper(name):
    """Load a kernel helper module by file location (cached)."""
    if name not in _MODULES:
        spec = importlib.util.spec_from_file_location(
            f"sf_kernel_{name}", SCRIPTS / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULES[name] = module
    return _MODULES[name]


def run(name, *args, stdin=None, cwd=None, env=None, timeout=120):
    """Run a kernel helper CLI exactly the way a validator would."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *(str(arg) for arg in args)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )


def notes():
    """A valid checkpoint note set."""
    return {
        "objective": "Ship story 1 with regression coverage",
        "next": "Run the regression suite",
        "completed": ["Evidence: report.json"],
        "decisions": ["D1: deferred follow-up, see source.md"],
        "open_questions": [],
    }


def imported_top_modules(path):
    """Every top-level module a Python source file imports."""
    found = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def non_stdlib_imports(path):
    """Imported modules that are not standard library (must be none for helpers)."""
    return sorted(
        name
        for name in imported_top_modules(path)
        if name not in sys.stdlib_module_names and not name.startswith("__")
    )


class Workspace:
    """A temporary consumer project with an active factory program."""

    def __init__(self, program="demo"):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup = None
        self.root = Path(self.temp.name).resolve()
        self.program = program
        (self.root / "principles.md").write_text("Authoritative project principles\n")
        (self.root / "tracker.yaml").write_text("stories: {}\n")
        result = self.run_state(
            "init",
            "--tracker",
            "tracker.yaml",
            "--principles",
            "principles.md",
            "--program",
            program,
        )
        assert result.returncode == 0, result.stderr

    def cleanup(self):
        self.temp.cleanup()

    # -- command surfaces --------------------------------------------------
    def run_state(self, *args, stdin=None, env=None):
        return run("state", "--workspace", self.root, *args, stdin=stdin, env=env)

    def claim(self, task, owner, repo, *paths, env=None):
        return self.run_state(
            "claim",
            "--task",
            task,
            "--owner",
            owner,
            "--repo",
            repo,
            "--paths",
            *paths,
            env=env,
        )

    def checkpoint(self, note_set, env=None):
        return self.run_state(
            "checkpoint", "--notes", self.notes_file(note_set), env=env
        )

    def snapshot(self, env=None):
        return self.run_state("snapshot", env=env)

    # -- files -------------------------------------------------------------
    def pointer_file(self):
        return self.root / POINTER

    def run_file(self):
        return self.root / ".software-factory" / "runs" / self.program / "run.json"

    def checkpoint_file(self):
        return self.run_file().with_name("CHECKPOINT.md")

    def runs_dir(self):
        return self.run_file().parent

    def state(self):
        return json.loads(self.run_file().read_text())

    def notes_file(self, note_set, name="notes.json"):
        path = self.root / name
        path.write_text(json.dumps(note_set))
        return path

    # -- git fixtures --------------------------------------------------------
    @staticmethod
    def git(repo, *args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def repo(self, name="repo", commit=True):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, "init", "-q", "-b", "main")
        if commit:
            (repo / "README.md").write_text("fixture\n")
            self.git(repo, "add", "-A")
            self.git(
                repo,
                "-c",
                f"user.email={FIXTURE_EMAIL}",
                "-c",
                f"user.name={FIXTURE_NAME}",
                "commit",
                "-q",
                "-m",
                "fixture commit",
            )
        return repo

    def worktree(self, repo, name="wt2"):
        path = self.root / name
        self.git(repo, "worktree", "add", str(path), "-b", f"fixture-{name}")
        return path


def guard_env():
    """PATH with host-CLI guard stubs that record every invocation and fail."""
    stub_dir = Path(tempfile.mkdtemp(prefix="sf-guards-"))
    log = stub_dir / "guard.log"
    for name in ("claude", "cursor-agent", "codex", "gemini"):
        script = stub_dir / name
        script.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$0 $*" >> "$SF_GUARD_LOG"\nexit 127\n'
        )
        script.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(stub_dir) + os.pathsep + env.get("PATH", "")
    env["SF_GUARD_LOG"] = str(log)
    return env, log, stub_dir


# -- installer fixtures ------------------------------------------------------
# Shared by tests/test_installer.py and tests/test_host_claude.py; they encode
# the shared harness of the validation contract (mkfresh/mkexisting, HOME
# sentinels, subprocess recorders, guard stubs).

INSTALLER = REPO / "install.py"

CLAUDE_SETTINGS_FIXTURE = (
    '{"model":"opus","env":{"TEAM_CITY":"1"},'
    '"permissions":{"allow":["Bash(npm test:*)"]},'
    '"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":'
    '[{"type":"command","command":"\\"$HOME/guard-user.sh\\""}]}]}}'
)
CURSOR_HOOKS_FIXTURE = (
    '{"version":1,"hooks":{"beforeShellExecution":'
    '[{"type":"command","command":"echo user"}]}}'
)


def run_installer(*args, cwd=None, env=None, timeout=120):
    """Run install.py exactly the way a validator would."""
    return subprocess.run(
        [sys.executable, str(INSTALLER), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )


def tree_hashes(root):
    """sha256 manifest of every regular file below root (repo-relative keys).

    The ``.git`` directory is Git's own state and never part of an
    installer tree comparison.
    """
    root = Path(root)
    hashes = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def recorder_env():
    """Guard stubs plus side-effect recorders for package/download tools.

    Returns (env, record_dir, guard_log). The recorders stand in for npx,
    node, npm, uv and curl; every invocation appends its argv to
    ``$SF_REC/<name>`` so tests can prove nothing was spawned. The guard
    stubs prove the host CLIs are never executed.
    """
    env, guard_log, stub_dir = guard_env()
    record_dir = Path(tempfile.mkdtemp(prefix="sf-rec-"))
    for name in ("npx", "node", "npm", "uv", "curl"):
        script = stub_dir / name
        script.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$0 $*" >> "$SF_REC/'
            + name
            + '"\nexit 0\n'
        )
        script.chmod(0o755)
    env["SF_REC"] = str(record_dir)
    return env, record_dir, guard_log


def home_sentinel(base):
    """A fake HOME with host-config sentinels; returns (home, snapshot)."""
    home = Path(base) / "home"
    sentinels = {
        ".claude/settings.json": '{"model":"sentinel"}\n',
        ".cursor/hooks.json": '{"version":1,"hooks":{}}\n',
        ".codex/config.toml": 'model = "sentinel"\n',
    }
    for rel, content in sentinels.items():
        path = home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def snapshot():
        return tree_hashes(home), sorted(
            str(p.relative_to(home)) for p in home.rglob("*")
        )

    return home, snapshot


def fresh_repo(base, name="repo"):
    """mkfresh: a git repo with one committed README and nothing else."""
    root = Path(base).resolve() / name
    root.mkdir(parents=True)
    Workspace.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("fixture\n")
    Workspace.git(root, "add", "-A")
    Workspace.git(
        root,
        "-c",
        f"user.email={FIXTURE_EMAIL}",
        "-c",
        f"user.name={FIXTURE_NAME}",
        "commit",
        "-q",
        "-m",
        "fixture commit",
    )
    return root


def existing_repo(base, name="repo"):
    """mkexisting: mkfresh plus realistic user-owned state (see contract)."""
    root = fresh_repo(base, name)
    (root / "CLAUDE.md").write_text(
        "# My Project\n\nHouse rules: keep diffs small and tested.\n"
    )
    (root / "AGENTS.md").write_text("# Notes\n\nWater the tests.\n")
    (root / ".gitignore").write_text("build/\n.env\n")
    (root / "notes.txt").write_text("tracked\n")
    Workspace.git(root, "add", "-A")
    Workspace.git(
        root,
        "-c",
        f"user.email={FIXTURE_EMAIL}",
        "-c",
        f"user.name={FIXTURE_NAME}",
        "commit",
        "-q",
        "-m",
        "user content",
    )
    (root / "notes.txt").write_text("tracked\nuser edit\n")  # dirty, uncommitted
    (root / "scratch.txt").write_text("untracked\n")
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(CLAUDE_SETTINGS_FIXTURE)
    cursor = root / ".cursor"
    cursor.mkdir()
    (cursor / "hooks.json").write_text(CURSOR_HOOKS_FIXTURE)
    return root
