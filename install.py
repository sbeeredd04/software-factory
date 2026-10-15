#!/usr/bin/env python3
"""Software Factory installer.

Projects the canonical pack (``skills/``, ``agents/``, the kernel helpers)
into a consumer repository for a coding-agent host, as one idempotent
transaction:

1. resolve the project root and refuse unsafe destinations (symlink
   escapes, non-regular targets, malformed JSON settings) before any write;
2. build an in-memory write plan with before/after hashes;
3. detect conflicts - unowned name collisions and locally modified managed
   files - which abort with zero writes unless the exact path is passed to
   ``--allow-overwrite``;
4. take a bounded installation lock, re-verify before-hashes, back up every
   overwritten file into ``.software-factory/backups/<install-id>/`` with
   private permissions, then apply each write atomically;
5. write the ownership manifest ``.software-factory/installation.json``
   last, after every validated write.

The installer never runs Git, never runs package managers, never touches
home-directory host configuration, and never creates runtime state
pointers (``active.json``/``state.lock``). It writes nothing inside the
committed ``.software-factory/context/`` home and ignores only the
volatile state paths in ``.gitignore``.

Standard library only (Python >= 3.11). Host projections are data-driven
from ``hosts/<host>/policy.json``; the Claude Code projection is the
reference implementation.
"""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import sys
import tempfile
import time
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent
PACK_NAME = "software-factory"
PACK_VERSION = "0.1.0"

STATE_DIR = ".software-factory"
MANIFEST_REL = f"{STATE_DIR}/installation.json"
LOCK_REL = f"{STATE_DIR}/.install.lock"
BACKUPS_REL = f"{STATE_DIR}/backups"
RUNTIME_REL = f"{STATE_DIR}/runtime"
RUNTIME_HELPERS = ("state.py", "gate.py", "hook.py", "config.py")
KERNEL_SCRIPTS = Path("skills/software-factory/scripts")

GITIGNORE_ENTRIES = (
    f"{STATE_DIR}/runtime/",
    f"{STATE_DIR}/backups/",
    f"{STATE_DIR}/runs/",
    f"{STATE_DIR}/active.json",
    f"{STATE_DIR}/state.lock",
    LOCK_REL,
    f"{STATE_DIR}/installation.json",
)

BLOCK_BEGIN = "<!-- software-factory:begin -->"
BLOCK_END = "<!-- software-factory:end -->"
CLAUDE_BLOCK = (
    "## Software Factory\n"
    "\n"
    "This project has the Software Factory pack installed for Claude Code.\n"
    "Start or resume factory work with the `software-factory` skill; its\n"
    "entry point is `.claude/skills/software-factory/SKILL.md`.\n"
    "Factory-owned files are listed in\n"
    "`.software-factory/installation.json`; runtime state lives under\n"
    "`.software-factory/` and is ignored except for the committed\n"
    "`context/` home.\n"
)
CODEX_BLOCK = (
    "## Software Factory\n"
    "\n"
    "This project has the Software Factory pack installed for Codex.\n"
    "Start or resume factory work with the `software-factory` skill\n"
    "(`$software-factory`); its entry point is\n"
    "`.agents/skills/software-factory/SKILL.md`.\n"
    "Factory-owned files are listed in\n"
    "`.software-factory/installation.json`; runtime state lives under\n"
    "`.software-factory/` and is ignored except for the committed\n"
    "`context/` home. Codex hooks run only after a one-time trust\n"
    "review: run `/hooks` and trust the factory hooks.\n"
    "Custom agents inherit the parent session permissions; reviewer\n"
    "instructions do not enforce a separate read-only sandbox. When enforced\n"
    "read-only review is required, verify an actually read-only parent/session\n"
    "or supported restriction before proceeding with dependent work.\n"
)
BLOCKS = {"CLAUDE.md": CLAUDE_BLOCK, "AGENTS.md": CODEX_BLOCK}

# (settings hook event, matcher, normalized hook.py event); Claude Code and
# Codex share this matcher-group shape.
HOOK_EVENTS = (
    ("SessionStart", "startup|resume|clear|compact", "session-start"),
    ("PreCompact", "manual|auto", "pre-compact"),
)
# (hooks.json event, normalized hook.py event); Cursor events are flat
# command entries with no matcher (sessionStart fires per conversation and
# the helper filters background agents itself).
CURSOR_HOOK_EVENTS = (
    ("sessionStart", "session-start"),
    ("preCompact", "pre-compact"),
)

LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05

# Host ids with a registered projector.
REGISTERED_HOSTS = ("claude-code", "cursor", "codex")
POLICY_DIRS = {"claude-code": "claude", "cursor": "cursor", "codex": "codex"}
# Project-directory markers and CLI binary names used by --host auto.
# Detection is `command -v` style (shutil.which): host binaries are never
# executed.
HOST_MARKERS = {"claude-code": ".claude", "cursor": ".cursor", "codex": ".codex"}
HOST_BINARIES = {"claude-code": "claude", "cursor": "cursor-agent",
                 "codex": "codex"}


class InstallError(Exception):
    """A refusal or failure that must abort the transaction with no writes."""


@dataclasses.dataclass
class Action:
    """One planned destination file."""

    path: str  # repo-relative, posix separators
    kind: str  # write | merge | block | gitignore
    content: bytes | None  # None for merge kinds until planned
    host: str | None


@dataclasses.dataclass
class PlannedFile:
    action: Action
    before: bytes | None
    after: bytes
    status: str  # create | write | merge | block | gitignore | noop
    backup: str | None = None

    @property
    def before_hash(self) -> str | None:
        return sha256(self.before) if self.before is not None else None

    @property
    def after_hash(self) -> str:
        return sha256(self.after)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(path: Path, rel: str) -> bytes | None:
    """Current bytes of a plan target; refuse anything that is not a file."""
    if path.is_symlink() and not path.exists():
        raise InstallError(f"broken symlink at {rel}; remove it manually")
    if not path.exists():
        return None
    if not path.is_file():
        raise InstallError(f"{rel} exists and is not a regular file; refusing")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InstallError(f"cannot read {rel}: {exc.strerror or exc}") from exc


def check_symlink_safety(root: Path, rel: str) -> None:
    """Refuse write paths that escape the project through a symlink."""
    current = root
    for part in Path(rel).parts:
        current = current / part
        if current.is_symlink():
            target = current.resolve()
            if target != root and root not in target.parents:
                raise InstallError(
                    f"symlink escape refused: {rel} resolves outside the project"
                )


def atomic_write(path: Path, content: bytes, created_dirs: set[Path]) -> None:
    parent = path.parent
    missing = []
    walk = parent
    while not walk.exists():
        missing.append(walk)
        walk = walk.parent
    parent.mkdir(parents=True, exist_ok=True)
    created_dirs.update(missing)
    fd, tmp = tempfile.mkstemp(dir=str(parent), prefix=".sf-tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- host policy and frontmatter projection ---------------------------------


def load_policy(host: str) -> dict:
    path = PACK_ROOT / "hosts" / POLICY_DIRS[host] / "policy.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"pack host policy is unreadable: {path.name}") from exc
    if not isinstance(policy, dict) or policy.get("host") != host:
        raise InstallError(f"pack host policy is invalid for {host}")
    return policy


def load_agent_policy(host: str) -> dict:
    path = PACK_ROOT / "hosts" / POLICY_DIRS[host] / "agent-policy.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"pack host policy is unreadable: {path.name}") from exc
    if not isinstance(policy, dict):
        raise InstallError(f"pack host policy is invalid for {host}")
    return policy


def frontmatter_close(lines: list[str], rel: str) -> int:
    """Index of the closing frontmatter fence; refuses a malformed block."""
    if not lines or lines[0].strip() != "---":
        raise InstallError(f"{rel}: missing frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index
    raise InstallError(f"{rel}: frontmatter never closes")


def inject_claude_frontmatter(content: bytes, skill: str, policy: dict) -> bytes:
    """Add Claude-only keys to a canonical SKILL.md; the body never changes."""
    text = content.decode("utf-8")
    lines = text.split("\n")
    closing = frontmatter_close(lines, f"skills/{skill}/SKILL.md")
    hint = policy["argument_hints"].get(skill, "[request]")
    extra = [f'argument-hint: "{hint}"']
    if skill in policy.get("explicit_only", []):
        extra.append("disable-model-invocation: true")
    lines[closing:closing] = extra
    return "\n".join(lines).encode()


def inject_cursor_readonly(content: bytes, role: str, policy: dict) -> bytes:
    """Add the Cursor readonly flag to a canonical agent; body never changes."""
    text = content.decode("utf-8")
    lines = text.split("\n")
    closing = frontmatter_close(lines, f"agents/{role}.md")
    readonly = "true" if role in set(policy.get("readonly", [])) else "false"
    insert_at = closing
    for index in range(1, closing):
        if lines[index].startswith("model:"):
            insert_at = index + 1
            break
    lines[insert_at:insert_at] = [f"readonly: {readonly}"]
    return "\n".join(lines).encode()


def parse_agent_frontmatter(path: Path) -> tuple[str, str, str]:
    """(name, description, body) of a canonical role agent."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    closing = frontmatter_close(lines, f"agents/{path.name}")
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        key, sep, raw = line.partition(":")
        if not sep:
            raise InstallError(f"agents/{path.name}: unparsable frontmatter line")
        fields[key.strip()] = raw.strip()
    name = fields.get("name", "")
    if name != path.stem:
        raise InstallError(f"agents/{path.name}: name does not match the file")
    if fields.get("model") != "inherit":
        raise InstallError(f"agents/{path.name}: canonical agents use model: inherit")
    raw_description = fields.get("description", "")
    if raw_description.startswith('"'):
        try:
            description = json.loads(raw_description)
        except json.JSONDecodeError as exc:
            raise InstallError(
                f"agents/{path.name}: bad description quoting"
            ) from exc
    else:
        description = raw_description
    if not description:
        raise InstallError(f"agents/{path.name}: missing description")
    body = "\n".join(lines[closing + 1 :]).lstrip("\n").rstrip("\n") + "\n"
    return name, description, body


def codex_agent_toml(path: Path) -> bytes:
    """Project canonical role intent; model and permissions inherit the parent.

    Custom-agent sandbox_mode cannot override parent permissions. Preserve
    reviewer instructions without claiming they create an enforced sandbox.
    """
    name, description, body = parse_agent_frontmatter(path)
    if "'''" in body:
        raise InstallError(f"agents/{path.name}: body cannot embed in TOML")
    text = (
        f"# Generated from agents/{name}.md by the Software Factory installer;\n"
        "# regenerate with install.py instead of editing by hand.\n"
        "# Permissions inherit the parent session; role instructions do not enforce isolation.\n"
        f"name = {json.dumps(name)}\n"
        f"description = {json.dumps(description)}\n"
        "developer_instructions = '''\n"
        f"{body}"
        "'''\n"
    )
    return text.encode()


def openai_yaml(skill: str, policy: dict) -> bytes:
    """The Codex ``agents/openai.yaml`` policy file for one skill.

    Written for the six entry/admin skills (``allow_implicit_invocation:
    false``) and for working skills with an interface declaration
    (``sf-crawl``, implicitly invocable like the design skills, which carry
    no policy file at all).
    """
    lines = [
        "# Generated by the Software Factory installer; canonical policy: "
        + "hosts/codex/policy.json."
    ]
    interface = policy.get("openai_interface", {}).get(skill)
    if interface:
        lines.append("interface:")
        for key in sorted(interface):
            lines.append(f'  {key}: "{interface[key]}"')
    explicit = skill in set(policy.get("explicit_only", []))
    lines.append("policy:")
    lines.append(
        f"  allow_implicit_invocation: {'false' if explicit else 'true'}"
    )
    return ("\n".join(lines) + "\n").encode()


def project_claude(root: Path, policy: dict, profile: str) -> list[Action]:
    """The Claude Code projection: skills, agents, hooks, pointer, runtime."""
    del root  # destinations are root-relative; only policy and profile matter
    actions: list[Action] = []
    skills_src = PACK_ROOT / "skills"
    for skill_dir in sorted(skills_src.iterdir()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        for src in sorted(skill_dir.rglob("*")):
            if not src.is_file():
                continue
            if "__pycache__" in src.parts or src.suffix == ".pyc":
                continue
            rel = src.relative_to(skills_src).as_posix()
            content = src.read_bytes()
            if src.name == "SKILL.md":
                content = inject_claude_frontmatter(content, skill_dir.name, policy)
            actions.append(Action(f".claude/skills/{rel}", "write", content,
                                  "claude-code"))
    if profile == "full":
        for src in sorted((PACK_ROOT / "agents").glob("sf-*.md")):
            actions.append(Action(f".claude/agents/{src.name}", "write",
                                  src.read_bytes(), "claude-code"))
        actions.extend(runtime_actions())
        actions.append(Action(".claude/settings.json", "merge", None,
                              "claude-code"))
        actions.append(Action("CLAUDE.md", "block", None, "claude-code"))
    actions.append(Action(".gitignore", "gitignore", None, None))
    return actions


def runtime_actions() -> list[Action]:
    """The host-neutral kernel helper copies under .software-factory/runtime/."""
    return [
        Action(
            f"{RUNTIME_REL}/{helper}",
            "write",
            (PACK_ROOT / KERNEL_SCRIPTS / helper).read_bytes(),
            None,
        )
        for helper in RUNTIME_HELPERS
    ]


def project_shared_skills(hosts: list[str]) -> list[Action]:
    """The one shared .agents/skills payload for Cursor and Codex.

    Apply each installed host's invocation policy to canonical sources.
    Cursor needs its explicit-only frontmatter flag; Codex needs openai.yaml.
    Combined Codex frontmatter tolerance and live host loading are unverified.
    """
    actions: list[Action] = []
    cursor_explicit = (
        set(load_policy("cursor").get("explicit_only", []))
        if "cursor" in hosts else set()
    )
    skills_src = PACK_ROOT / "skills"
    for skill_dir in sorted(skills_src.iterdir()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        for src in sorted(skill_dir.rglob("*")):
            if not src.is_file():
                continue
            if "__pycache__" in src.parts or src.suffix == ".pyc":
                continue
            rel = src.relative_to(skills_src).as_posix()
            content = src.read_bytes()
            if src.name == "SKILL.md" and skill_dir.name in cursor_explicit:
                lines = content.decode("utf-8").split("\n")
                closing = frontmatter_close(lines, f"skills/{rel}")
                lines[closing:closing] = ["disable-model-invocation: true"]
                content = "\n".join(lines).encode()
            actions.append(
                Action(f".agents/skills/{rel}", "write", content, None)
            )
    if "codex" in hosts:
        codex_policy = load_policy("codex")
        policy_skills = set(codex_policy.get("explicit_only", [])) | set(
            codex_policy.get("openai_interface", {})
        )
        for skill in sorted(policy_skills):
            actions.append(
                Action(
                    f".agents/skills/{skill}/agents/openai.yaml",
                    "write",
                    openai_yaml(skill, codex_policy),
                    None,
                )
            )
    return actions


def project_cursor(root: Path, policy: dict, profile: str) -> list[Action]:
    """The Cursor projection: readonly-matrix agents, hooks v1, .mdc rule.

    The skills payload is shared with Codex and planned once per install
    by build_plan (project_shared_skills).
    """
    del root, policy  # destinations are root-relative; policy already loaded
    actions: list[Action] = []
    if profile == "full":
        agent_policy = load_agent_policy("cursor")
        for src in sorted((PACK_ROOT / "agents").glob("sf-*.md")):
            actions.append(Action(
                f".cursor/agents/{src.name}", "write",
                inject_cursor_readonly(src.read_bytes(), src.stem, agent_policy),
                "cursor"))
        actions.extend(runtime_actions())
        actions.append(Action(".cursor/hooks.json", "merge", None, "cursor"))
        rule = (PACK_ROOT / "hosts" / "cursor" / "factory.mdc").read_bytes()
        actions.append(Action(
            ".cursor/rules/software-factory.mdc", "write", rule, "cursor"))
    actions.append(Action(".gitignore", "gitignore", None, None))
    return actions


def project_codex(root: Path, policy: dict, profile: str) -> list[Action]:
    """The Codex projection: TOML agents, hooks.json, the AGENTS.md block.

    The skills payload is shared with Cursor and planned once per install
    by build_plan (project_shared_skills).
    """
    del root, policy
    actions: list[Action] = []
    if profile == "full":
        for src in sorted((PACK_ROOT / "agents").glob("sf-*.md")):
            actions.append(Action(
                f".codex/agents/{src.stem}.toml", "write",
                codex_agent_toml(src), "codex"))
        actions.extend(runtime_actions())
        actions.append(Action(".codex/hooks.json", "merge", None, "codex"))
        actions.append(Action("AGENTS.md", "block", None, "codex"))
    actions.append(Action(".gitignore", "gitignore", None, None))
    return actions


PROJECTORS = {
    "claude-code": project_claude,
    "cursor": project_cursor,
    "codex": project_codex,
}


# -- merge kinds -------------------------------------------------------------


def detect_python() -> str:
    """Keep the interpreter that successfully ran this Python >=3.11 installer.

    PATH may contain an older Python or a different environment. Preserve
    executable symlinks so virtual environments keep their intended runtime.
    """
    if sys.version_info < (3, 11) or not sys.executable:
        raise InstallError("run the installer with Python 3.11 or newer")
    executable = Path(sys.executable).absolute()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise InstallError("installer Python is unavailable; reinstall with Python 3.11 or newer")
    return str(executable)


def hook_command(root: Path, host: str, event: str) -> str:
    """The installed hook command; stderr merges into stdout (2>&1) so the
    sanitized recovery warning is observable on stdout (VAL-HOST-018)."""
    script = root / RUNTIME_REL / "hook.py"
    command = shlex.join([
        detect_python(), str(script), "--host", host, "--event", event,
        "--workspace", str(root),
    ])
    return f"{command} 2>&1"


def is_owned_handler(handler: object, host: str, event: str) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command", ""))
    return (
        f"{RUNTIME_REL}/hook.py" in command
        and f"--host {host}" in command
        and f"--event {event}" in command
    )


def parse_json_document(current: bytes | None, rel: str) -> dict:
    """Parse a JSON settings/hooks document; refuse malformed bytes as-is."""
    if current is None:
        return {}
    try:
        doc = json.loads(current.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(
            f"{rel} is malformed ({exc}); fix or remove it manually"
        ) from exc
    if not isinstance(doc, dict):
        raise InstallError(f"{rel} must contain a JSON object; refusing")
    return doc


def merge_event_groups(hooks: dict, root: Path, host: str, rel: str) -> None:
    """Fold one owned command group per event into a matcher-group map."""
    for event, matcher, normalized in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise InstallError(f"{rel}: 'hooks.{event}' is not a list; refusing")
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise InstallError(
                    f"{rel}: 'hooks.{event}' has a malformed group; refusing"
                )
            handlers = [
                handler
                for handler in group["hooks"]
                if not is_owned_handler(handler, host, normalized)
            ]
            if handlers or not group["hooks"]:
                if len(handlers) != len(group["hooks"]):
                    group = dict(group)
                    group["hooks"] = handlers
                kept.append(group)
        kept.append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command(root, host, normalized),
                    }
                ],
            }
        )
        hooks[event] = kept


def merge_settings(current: bytes | None, root: Path, host: str) -> bytes:
    """Add owned hook entries to Claude settings, preserving all user data."""
    rel = ".claude/settings.json"
    settings = parse_json_document(current, rel)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"{rel}: 'hooks' is not an object; refusing")
    merge_event_groups(hooks, root, host, rel)
    return (json.dumps(settings, indent=2) + "\n").encode()


def merge_codex_hooks(current: bytes | None, root: Path) -> bytes:
    """Codex hooks.json: the same matcher-group shape as Claude settings,
    at the top level, preserving every user group and unrelated key."""
    rel = ".codex/hooks.json"
    doc = parse_json_document(current, rel)
    hooks = doc.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"{rel}: 'hooks' is not an object; refusing")
    merge_event_groups(hooks, root, "codex", rel)
    return (json.dumps(doc, indent=2) + "\n").encode()


def merge_cursor_hooks(current: bytes | None, root: Path) -> bytes:
    """Cursor hooks.json v1: flat command entries without matchers.

    The user's version and unrelated events (e.g. beforeShellExecution)
    survive byte-value-identical; exactly one owned entry per event.
    """
    rel = ".cursor/hooks.json"
    doc = parse_json_document(current, rel)
    version = doc.get("version", 1)
    if version != 1:
        raise InstallError(
            f"{rel}: unsupported hooks version {version!r}; refusing to merge"
        )
    doc["version"] = 1
    hooks = doc.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"{rel}: 'hooks' is not an object; refusing")
    for event, normalized in CURSOR_HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise InstallError(f"{rel}: 'hooks.{event}' is not a list; refusing")
        kept = [
            entry
            for entry in entries
            if not is_owned_handler(entry, "cursor", normalized)
        ]
        kept.append(
            {
                "type": "command",
                "command": hook_command(root, "cursor", normalized),
            }
        )
        hooks[event] = kept
    return (json.dumps(doc, indent=2) + "\n").encode()


def merge_block(current: bytes | None, rel: str) -> bytes:
    """Insert or refresh the factory managed block; never touch user text."""
    block = f"{BLOCK_BEGIN}\n{BLOCKS[rel]}{BLOCK_END}\n"
    if current is None:
        return block.encode()
    try:
        text = current.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError(f"{rel} is not UTF-8 text; refusing") from exc
    begins = text.count(BLOCK_BEGIN)
    ends = text.count(BLOCK_END)
    if begins == 0 and ends == 0:
        separator = "" if not text or text.endswith("\n") else "\n"
        return (text + separator + block).encode()
    lines = text.split("\n")
    begin_lines = [i for i, line in enumerate(lines) if BLOCK_BEGIN in line]
    end_lines = [i for i, line in enumerate(lines) if BLOCK_END in line]
    if (
        begins == 1
        and ends == 1
        and len(begin_lines) == 1
        and len(end_lines) == 1
        and begin_lines[0] < end_lines[0]
    ):
        lines[begin_lines[0] : end_lines[0] + 1] = block.rstrip("\n").split("\n")
        return "\n".join(lines).encode()
    raise InstallError(
        f"{rel}: ambiguous managed block (missing or duplicate "
        "software-factory markers); fix or remove the markers manually"
    )


def merge_gitignore(current: bytes | None) -> bytes:
    """Append the volatile state entries; user lines survive byte-identical."""
    if current is None:
        return ("\n".join(GITIGNORE_ENTRIES) + "\n").encode()
    try:
        text = current.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError(".gitignore is not UTF-8 text; refusing") from exc
    present = text.split("\n")
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in present]
    if not missing:
        return current
    if text and not text.endswith("\n"):
        text += "\n"
    return (text + "\n".join(missing) + "\n").encode()


def compute_content(action: Action, root: Path, before: bytes | None) -> bytes:
    if action.kind == "merge":
        if action.path == ".claude/settings.json":
            return merge_settings(before, root, action.host or "claude-code")
        if action.path == ".cursor/hooks.json":
            return merge_cursor_hooks(before, root)
        if action.path == ".codex/hooks.json":
            return merge_codex_hooks(before, root)
        raise InstallError(f"internal error: no merge handler for {action.path}")
    if action.kind == "block":
        return merge_block(before, action.path)
    if action.kind == "gitignore":
        return merge_gitignore(before)
    if action.content is None:
        raise InstallError(f"internal error: no content for {action.path}")
    return action.content


# -- manifest ----------------------------------------------------------------


def load_manifest(root: Path) -> dict | None:
    path = root / MANIFEST_REL
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(
            f"{MANIFEST_REL} is unreadable or malformed; restore it or remove "
            "it manually before installing"
        ) from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise InstallError(f"{MANIFEST_REL} has an invalid shape; refusing")
    return manifest


def build_manifest(
    planned: list[PlannedFile],
    previous: dict | None,
    hosts: list[str],
    profile: str,
    install_id: str,
) -> dict:
    """Extend ownership without adopting edits outside the current plan.

    Installs are additive: selecting another host or skills-only profile
    does not uninstall earlier projections. Preserve their recorded hashes
    and backups, even if those files have since been changed or removed.
    The profile records the fullest installed payload, not a downgrade.
    """
    prior = {}
    if previous:
        for entry in previous.get("files", []):
            if isinstance(entry, dict) and "path" in entry:
                prior[entry["path"]] = entry
    files_by_path = dict(prior)
    for item in planned:
        backup = item.backup
        if backup is None:
            backup = prior.get(item.action.path, {}).get("backup")
        prior_entry = prior.get(item.action.path)
        # Keep the original user restoration basis independent of rollback
        # backups from later updates. Legacy manifests cannot prove it.
        restoration = (prior_entry or {}).get("restore", "unverified")
        if prior_entry is None:
            restoration = (
                {"path": item.backup, "sha256": item.before_hash}
                if item.backup is not None else
                None if item.before is None else "unverified"
            )
        files_by_path[item.action.path] = {
            "path": item.action.path,
            "sha256": item.after_hash,
            "action": item.action.kind,
            "host": item.action.host,
            "backup": backup,
            **({"restore": restoration} if restoration != "unverified" else {}),
        }
    files = sorted(files_by_path.values(), key=lambda entry: entry["path"])
    installed_hosts = set(hosts) | set((previous or {}).get("hosts", []))
    return {
        "version": 1,
        "install_id": install_id,
        "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pack": {"name": PACK_NAME, "version": PACK_VERSION},
        "hosts": [host for host in REGISTERED_HOSTS if host in installed_hosts],
        "profile": "full" if (previous or {}).get("profile") == "full" else profile,
        "files": files,
    }


# -- planning ----------------------------------------------------------------


def normalize_overwrite_paths(paths: list[str]) -> set[str]:
    normalized = set()
    for raw in paths:
        rel = raw.removeprefix("./").removesuffix("/")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise InstallError(f"invalid --allow-overwrite path: {raw}")
        normalized.add(rel)
    return normalized


def build_plan(
    root: Path,
    hosts: list[str],
    profile: str,
    allow: set[str],
) -> tuple[list[PlannedFile], list[str], dict | None]:
    """Build the full plan; merge-kind refusals raise before any write."""
    previous = load_manifest(root)
    installed_hosts = set(hosts) | set((previous or {}).get("hosts", []))
    actions: list[Action] = []
    for host in hosts:
        actions.extend(PROJECTORS[host](root, load_policy(host), profile))
    if any(host in ("cursor", "codex") for host in hosts):
        actions.extend(project_shared_skills(sorted(installed_hosts)))
    # Collapse duplicate destinations (runtime helpers, .gitignore) emitted
    # by more than one projector; identical content is shared, divergent
    # content is an internal error.
    unique: list[Action] = []
    seen_paths: dict[str, Action] = {}
    for action in actions:
        previous_action = seen_paths.get(action.path)
        if previous_action is not None:
            if (previous_action.kind, previous_action.content) != (
                action.kind,
                action.content,
            ):
                raise InstallError(
                    f"internal error: conflicting plan for {action.path}"
                )
            continue
        seen_paths[action.path] = action
        unique.append(action)
    actions = unique
    owned = {}
    if previous:
        for entry in previous.get("files", []):
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                owned[entry["path"]] = entry
    planned: list[PlannedFile] = []
    conflicts: list[str] = []
    covered: set[str] = set()
    for action in actions:
        rel = action.path
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise InstallError(f"internal error: unsafe plan path {rel}")
        check_symlink_safety(root, rel)
        before = read_file(root / rel, rel)
        after = compute_content(action, root, before)
        conflict = None
        if before is None:
            status = "create"
        elif action.kind == "write":
            entry = owned.get(rel)
            if entry is None:
                conflict = f"{rel} exists and is not owned by this installation"
            elif entry.get("sha256") != sha256(before):
                conflict = f"{rel} was installed by the factory but modified locally"
            status = "noop" if sha256(before) == sha256(after) else "write"
        else:
            # Merge kinds fold owned entries into user files structurally;
            # user edits elsewhere in the file are preserved, never conflicts.
            status = "noop" if sha256(before) == sha256(after) else action.kind
        if conflict:
            if rel in allow:
                covered.add(rel)
            else:
                conflicts.append(
                    f"{conflict}; pass --allow-overwrite {rel} to replace it "
                    "(a private backup is written first)"
                )
        planned.append(PlannedFile(action, before, after, status))
    for unused in sorted(allow - covered):
        conflicts.append(
            f"--allow-overwrite {unused} does not match any conflicting path"
        )
    return planned, conflicts, previous


# -- apply -------------------------------------------------------------------


def write_backup(root: Path, install_id: str, item: PlannedFile) -> str:
    rel_backup = f"{BACKUPS_REL}/{install_id}/{item.action.path}"
    dest = root / rel_backup
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, item.before or b"", set())
    os.chmod(dest, 0o600)
    base = root / BACKUPS_REL
    walk = dest.parent
    while True:
        os.chmod(walk, 0o700)
        if walk == base:
            break
        walk = walk.parent
    return rel_backup


def acquire_lock(root: Path, created_dirs: set[Path]):
    """Take the bounded installation lock; returns the lock fd and path."""
    state_dir = root / STATE_DIR
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir(STATE_DIR, dir_fd=root_fd)
            created_dirs.add(state_dir)
        except FileExistsError:
            pass
        state_fd = os.open(STATE_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=root_fd)
        try:
            fd = os.open(Path(LOCK_REL).name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                         0o600, dir_fd=state_fd)
        finally:
            os.close(state_fd)
    finally:
        os.close(root_fd)
    lock_path = root / LOCK_REL
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise InstallError(
                    "another installation is in progress; try again shortly"
                ) from None
            time.sleep(LOCK_POLL_SECONDS)
    return fd, lock_path


def rollback(
    root: Path, applied: list[PlannedFile], created_dirs: set[Path]
) -> None:
    """Undo this transaction's writes where the bytes are still ours."""
    for item in reversed(applied):
        target = root / item.action.path
        try:
            current = target.read_bytes() if target.is_file() else None
        except OSError:
            continue
        if current is None or sha256(current) != item.after_hash:
            continue  # a concurrent edit; never clobber it
        if item.backup is not None:
            backup = root / item.backup
            if backup.is_file():
                atomic_write(target, backup.read_bytes(), set())
        else:
            try:
                target.unlink()
            except OSError:
                pass
    for directory in sorted(created_dirs, key=lambda p: -len(p.parts)):
        try:
            directory.rmdir()  # only removes directories that are empty
        except OSError:
            pass


def apply_plan(
    root: Path,
    planned: list[PlannedFile],
    previous: dict | None,
    hosts: list[str],
    profile: str,
) -> None:
    created_dirs: set[Path] = set()
    fd, _lock_path = acquire_lock(root, created_dirs)
    applied: list[PlannedFile] = []
    try:
        if load_manifest(root) != previous:
            raise InstallError("installation ownership changed while planning; retry")
        for item in planned:  # re-verify before-hashes under the lock
            current = read_file(root / item.action.path, item.action.path)
            current_hash = sha256(current) if current is not None else None
            if current_hash != item.before_hash:
                raise InstallError(
                    f"{item.action.path} changed while installing; retry"
                )
        install_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        try:
            for item in planned:
                if item.status == "noop":
                    continue
                if item.before is not None:
                    item.backup = write_backup(root, install_id, item)
                atomic_write(root / item.action.path, item.after, created_dirs)
                applied.append(item)
            manifest = build_manifest(planned, previous, hosts, profile, install_id)
            atomic_write(
                root / MANIFEST_REL,
                (json.dumps(manifest, indent=2) + "\n").encode(),
                created_dirs,
            )
        except BaseException:
            rollback(root, applied, created_dirs)
            raise
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        # Keep a stable inode: unlinking lets a later writer lock a new file
        # while an already waiting writer still owns the old one.


# -- plugin/project stacking ---------------------------------------------------
# A plugin install and a project projection for the same host are
# alternatives; stacking them double-loads every skill and hook.


def plugin_enabled_claude(root: Path) -> str | None:
    path = root / ".claude/settings.json"
    if not path.is_file():
        return None
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None  # malformed settings are refused by the merge itself
    if not isinstance(settings, dict):
        return None
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return None
    for key, value in enabled.items():
        if isinstance(key, str) and key.startswith(f"{PACK_NAME}@") and value:
            return ".claude/settings.json"
    return None


def plugin_enabled_codex(root: Path) -> str | None:
    path = root / ".codex/config.toml"
    if not path.is_file():
        return None
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None  # the installer never writes config.toml; leave it alone
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return None
    for key, value in plugins.items():
        if (
            isinstance(key, str)
            and key.startswith(f"{PACK_NAME}@")
            and isinstance(value, dict)
            and value.get("enabled")
        ):
            return ".codex/config.toml"
    return None


# Cursor has no documented project-scope enabled-plugin store; only hosts
# with a detectable marker refuse stacking.
PLUGIN_DETECTORS = {
    "claude-code": plugin_enabled_claude,
    "codex": plugin_enabled_codex,
}


def check_plugin_stacking(root: Path, hosts: list[str]) -> None:
    """Refuse to stack a project projection on an enabled factory plugin."""
    for host in hosts:
        detector = PLUGIN_DETECTORS.get(host)
        if detector is None:
            continue
        source = detector(root)
        if source is not None:
            raise InstallError(
                f"a {PACK_NAME} plugin is already enabled for {host} in "
                f"{source}; a plugin install and a project projection are "
                "alternatives - migration: disable the plugin entry (or "
                "uninstall the plugin), then rerun this install; nothing "
                "was written"
            )


# -- command surface -----------------------------------------------------------


def resolve_hosts(selection: str, root: Path) -> list[str]:
    parts = [part.strip() for part in selection.split(",") if part.strip()]
    if not parts:
        raise InstallError("empty host selection")
    resolved: list[str] = []
    for part in parts:
        if part == "all":
            for host in REGISTERED_HOSTS:
                if host not in resolved:
                    resolved.append(host)
        elif part == "auto":
            detected = auto_detect(root)
            if detected not in resolved:
                resolved.append(detected)
        elif part in REGISTERED_HOSTS:
            if part not in resolved:
                resolved.append(part)
        else:
            known = ", ".join((*REGISTERED_HOSTS, "all", "auto"))
            raise InstallError(f"unknown host '{part}' (supported: {known})")
    return resolved


def auto_detect(root: Path) -> str:
    """Pick a host from project markers, then available binaries.

    Project directories are the stronger signal; host binaries are only a
    ``command -v``-style presence check (shutil.which) and are never
    executed. An ambiguous or empty result demands an explicit --host.
    """
    markers = [
        host for host in REGISTERED_HOSTS if (root / HOST_MARKERS[host]).exists()
    ]
    if len(markers) == 1:
        print(
            f"install: auto-detected host {markers[0]} "
            f"(project {HOST_MARKERS[markers[0]]}/)"
        )
        return markers[0]
    if len(markers) > 1:
        raise InstallError(
            "multiple hosts detected ("
            + ", ".join(markers)
            + "); pass --host explicitly to choose"
        )
    available = [
        host for host in REGISTERED_HOSTS if shutil.which(HOST_BINARIES[host])
    ]
    if len(available) == 1:
        print(
            f"install: auto-detected host {available[0]} "
            f"({HOST_BINARIES[available[0]]} on PATH)"
        )
        return available[0]
    if available:
        raise InstallError(
            "multiple host binaries on PATH ("
            + ", ".join(available)
            + ") and no project markers; pass --host explicitly to choose"
        )
    raise InstallError(
        "no host detected in this project; pass --host explicitly"
    )


def format_plan(planned: list[PlannedFile]) -> list[str]:
    lines = []
    for item in planned:
        if item.status == "noop":
            continue
        lines.append(f"  {item.status} {item.action.path}")
    return lines


def cmd_install(args: argparse.Namespace) -> int:
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        raise InstallError(f"project directory does not exist: {args.project}")
    hosts = resolve_hosts(args.host, root)
    check_plugin_stacking(root, hosts)
    allow = normalize_overwrite_paths(args.allow_overwrite)
    planned, conflicts, previous = build_plan(root, hosts, args.profile, allow)
    if conflicts:
        for conflict in conflicts:
            print(f"install: conflict: {conflict}", file=sys.stderr)
        return 1
    installed_hosts = set(hosts) | set((previous or {}).get("hosts", []))
    if "codex" in installed_hosts:
        print("install: Codex custom agents inherit parent permissions; "
              "role instructions do not enforce a separate read-only sandbox. "
              "Live custom-agent loading is unverified.")
    if {"cursor", "codex"} <= installed_hosts:
        print("install: shared Cursor/Codex skills carry both invocation policies; "
              "Codex tolerance of Cursor frontmatter and combined live host "
              "loading are unverified.")
    if args.dry_run:
        print(f"install plan (dry-run): host {', '.join(hosts)}, "
              f"profile {args.profile}")
        for line in format_plan(planned):
            print(line)
        print(f"install: dry-run complete; "
              f"{sum(1 for i in planned if i.status != 'noop')} destination(s); "
              "no changes written")
        return 0
    changes = [item for item in planned if item.status != "noop"]
    manifest = build_manifest(planned, previous, hosts, args.profile, "")
    metadata_changed = previous is None or any(
        manifest[key] != previous.get(key) for key in ("hosts", "profile", "files")
    )
    if not changes and not metadata_changed:
        print(f"install: 0 changes ({len(planned)} files already current)")
        return 0
    apply_plan(root, planned, previous, hosts, args.profile)
    for line in format_plan(planned):
        print(line)
    current = sum(1 for item in planned if item.status == "noop")
    print(f"install: {len(changes)} change(s) applied "
          f"({current} already current); manifest {MANIFEST_REL}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description=(
            "Install the Software Factory pack into a project's coding-agent "
            "host configuration. Standard library only; never runs Git, "
            "package managers (unless provisioning BMad), or host CLIs."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser(
        "install", help="install host projections into a project"
    )
    install.add_argument("--project", type=Path, required=True,
                         help="consumer project root")
    install.add_argument("--host", required=True,
                         help="claude-code, cursor, codex, a comma list, "
                              "all, or auto")
    install.add_argument("--dry-run", action="store_true",
                         help="print the plan; write nothing, spawn nothing")
    install.add_argument("--skip-bmad", action="store_true",
                         help="do not provision BMad Method")
    install.add_argument("--allow-overwrite", action="append", default=[],
                         metavar="PATH",
                         help="authorize overwriting a conflicting path "
                              "(repeatable); a backup is written first")
    install.add_argument("--profile", choices=("full", "skills-only"),
                         default="full",
                         help="full projection or skills only")
    uninstall = sub.add_parser("uninstall", help="remove unchanged owned projections")
    uninstall.add_argument("--project", type=Path, required=True)
    uninstall.add_argument("--host", default="all", help="selected hosts or all")
    uninstall.add_argument("--dry-run", action="store_true")
    doctor = sub.add_parser("doctor", help="read-only installation diagnostics")
    doctor.add_argument("--project", type=Path, required=True)
    doctor.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            return cmd_install(args)
        # Read-only diagnostics and uninstall dry-runs must not write caches
        # into the source pack when loading their shared implementation.
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location(
            "sf_install_lifecycle", PACK_ROOT / "scripts/install_lifecycle.py"
        )
        lifecycle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lifecycle)
        return getattr(lifecycle, args.command)(args, sys.modules[__name__])
    except InstallError as exc:
        print(f"install: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
