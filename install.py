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
import json
import os
import shutil
import sys
import tempfile
import time
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

# (settings hook event, matcher, normalized hook.py event)
HOOK_EVENTS = (
    ("SessionStart", "startup|resume|clear|compact", "session-start"),
    ("PreCompact", "manual|auto", "pre-compact"),
)

LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05

# Host ids with a registered projector. Cursor and Codex register here in
# their own milestone feature; the selection plumbing already supports them.
REGISTERED_HOSTS = ("claude-code",)
POLICY_DIRS = {"claude-code": "claude"}


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


def inject_claude_frontmatter(content: bytes, skill: str, policy: dict) -> bytes:
    """Add Claude-only keys to a canonical SKILL.md; the body never changes."""
    text = content.decode("utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise InstallError(f"skill {skill}: SKILL.md is missing frontmatter")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise InstallError(f"skill {skill}: SKILL.md frontmatter never closes")
    hint = policy["argument_hints"].get(skill, "[request]")
    extra = [f'argument-hint: "{hint}"']
    if skill in policy.get("explicit_only", []):
        extra.append("disable-model-invocation: true")
    lines[closing:closing] = extra
    return "\n".join(lines).encode()


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
        for helper in RUNTIME_HELPERS:
            src = PACK_ROOT / KERNEL_SCRIPTS / helper
            actions.append(Action(f"{RUNTIME_REL}/{helper}", "write",
                                  src.read_bytes(), None))
        actions.append(Action(".claude/settings.json", "merge", None,
                              "claude-code"))
        actions.append(Action("CLAUDE.md", "block", None, "claude-code"))
    actions.append(Action(".gitignore", "gitignore", None, None))
    return actions


PROJECTORS = {"claude-code": project_claude}


# -- merge kinds -------------------------------------------------------------


def detect_python() -> str:
    return shutil.which("python3") or sys.executable


def hook_command(root: Path, host: str, event: str) -> str:
    """The installed hook command; stderr merges into stdout (2>&1) so the
    sanitized recovery warning is observable on stdout (VAL-HOST-018)."""
    script = root / RUNTIME_REL / "hook.py"
    return f'"{detect_python()}" "{script}" --host {host} --event {event} 2>&1'


def is_owned_handler(handler: object, host: str, event: str) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command", ""))
    return (
        f"{RUNTIME_REL}/hook.py" in command
        and f"--host {host}" in command
        and f"--event {event}" in command
    )


def merge_settings(current: bytes | None, root: Path, host: str) -> bytes:
    """Add owned hook entries to Claude settings, preserving all user data."""
    rel = ".claude/settings.json"
    if current is None:
        settings: dict = {}
    else:
        try:
            settings = json.loads(current.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InstallError(
                f"{rel} is malformed ({exc}); fix or remove it manually"
            ) from exc
        if not isinstance(settings, dict):
            raise InstallError(f"{rel} must contain a JSON object; refusing")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError(f"{rel}: 'hooks' is not an object; refusing")
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
    return (json.dumps(settings, indent=2) + "\n").encode()


def block_text() -> str:
    return f"{BLOCK_BEGIN}\n{CLAUDE_BLOCK}{BLOCK_END}\n"


def merge_block(current: bytes | None, rel: str) -> bytes:
    """Insert or refresh the factory managed block; never touch user text."""
    block = block_text()
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
        return merge_settings(before, root, action.host or "claude-code")
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
    prior = {}
    if previous:
        for entry in previous.get("files", []):
            if isinstance(entry, dict) and "path" in entry:
                prior[entry["path"]] = entry
    files = []
    for item in planned:
        backup = item.backup
        if backup is None:
            backup = prior.get(item.action.path, {}).get("backup")
        files.append(
            {
                "path": item.action.path,
                "sha256": item.after_hash,
                "action": item.action.kind,
                "host": item.action.host,
                "backup": backup,
            }
        )
    files.sort(key=lambda entry: entry["path"])
    return {
        "version": 1,
        "install_id": install_id,
        "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pack": {"name": PACK_NAME, "version": PACK_VERSION},
        "hosts": hosts,
        "profile": profile,
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
    actions: list[Action] = []
    for host in hosts:
        actions.extend(PROJECTORS[host](root, load_policy(host), profile))
    previous = load_manifest(root)
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
    if not state_dir.exists():
        state_dir.mkdir()
        created_dirs.add(state_dir)
    lock_path = root / LOCK_REL
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
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
    fd, lock_path = acquire_lock(root, created_dirs)
    applied: list[PlannedFile] = []
    try:
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
        try:
            lock_path.unlink()
        except OSError:
            pass


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
    """Inspect project markers only; never executes a host binary."""
    markers = [
        host for host in REGISTERED_HOSTS if (root / f".{POLICY_DIRS[host]}").exists()
    ]
    if not markers:
        raise InstallError(
            "no host detected in this project; pass --host explicitly"
        )
    if len(markers) > 1:
        raise InstallError(
            "multiple hosts detected; pass --host explicitly to choose"
        )
    print(f"install: auto-detected host {markers[0]}")
    return markers[0]


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
    allow = normalize_overwrite_paths(args.allow_overwrite)
    planned, conflicts, previous = build_plan(root, hosts, args.profile, allow)
    if conflicts:
        for conflict in conflicts:
            print(f"install: conflict: {conflict}", file=sys.stderr)
        return 1
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
    if not changes:
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
                         help="claude-code, a comma list, all, or auto")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            return cmd_install(args)
    except InstallError as exc:
        print(f"install: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
