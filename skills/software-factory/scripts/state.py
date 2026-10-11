"""Local execution state for the Software Factory kernel.

Owns the active-program pointer, exclusive path claims and checkpoint notes
under a consumer project's `.software-factory/` directory. Standard library
only. It observes Git read-only and never calls models, the network or any
Git writer, and never dispatches work.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SECRET = re.compile(
    r"sk-ant-[\w-]+|gh[pousr]_[\w]+|-----BEGIN .*PRIVATE KEY-----|"
    r"\b(?:password|api_key|access_token|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
STATE_DIR = ".software-factory"
LOCK_WAIT_SECONDS = 5.0


class StateError(ValueError):
    pass


def now():
    return datetime.now(UTC).isoformat()


def within(root: Path, path: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise StateError("path escapes workspace")
    return path


def state_dir(workspace: Path) -> Path:
    return within(workspace, workspace / STATE_DIR)


def pointer_path(workspace: Path) -> Path:
    return state_dir(workspace) / "active.json"


def run_path(workspace: Path, program: str) -> Path:
    return within(workspace, workspace / STATE_DIR / "runs" / program) / "run.json"


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".factory-")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, data: dict):
    atomic_text(path, json.dumps(data, indent=2) + "\n")


@contextmanager
def locked(workspace: Path):
    directory = state_dir(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "state.lock").open("a") as stream:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StateError("state busy; reconcile the active writer")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def git(repo: Path, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        raise StateError("repository observation failed; verify the worktree")
    return result.stdout.strip()


def read_json(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise StateError("missing or invalid state; reconcile before continuing") from exc
    if not isinstance(data, dict):
        raise StateError("state must be an object")
    return data


def load(workspace):
    pointer_file = pointer_path(workspace)
    if not pointer_file.is_file():
        raise StateError("no active program pointer; reconcile by initializing a program or repairing state")
    pointer = read_json(pointer_file)
    if pointer.get("version") != 1:
        raise StateError("unsupported active pointer")
    relative = pointer.get("run")
    if not isinstance(relative, str):
        raise StateError("invalid active pointer")
    path = within(workspace, workspace / relative)
    data = read_json(path)
    validate_state(data)
    return path, data


def validate_state(data):
    if data.get("version") != 1 or not isinstance(data.get("claims"), dict):
        raise StateError("unsupported execution state")
    for key in ("program", "tracker", "principles"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise StateError("missing execution source fields")
    if not SLUG.fullmatch(data["program"]) or not isinstance(data.get("checkpoint"), dict):
        raise StateError("invalid program/checkpoint")
    if data["checkpoint"]:
        validate_notes(data["checkpoint"])
    for task, item in data["claims"].items():
        if not isinstance(task, str) or not isinstance(item, dict):
            raise StateError("invalid claim")
        for key in ("owner", "repo", "identity", "claimed_at"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise StateError("invalid claim fields")
        if not isinstance(item.get("paths"), list) or not all(
            isinstance(path, str) and path for path in item["paths"]
        ):
            raise StateError("invalid claim scope")
        if "observation" in item and not isinstance(item["observation"], dict):
            raise StateError("invalid claim observation")


def projection(data):
    notes = data.get("checkpoint") or {}
    rows = [
        f"# Software Factory checkpoint: {data['program']}",
        f"Updated: {data.get('updated_at', 'unknown')}",
        f"Canonical tracker: {data['tracker']}",
        f"Principles: {data['principles']}",
        f"Objective: {notes.get('objective', 'Read the checkpoint and reconcile')}",
        f"Next: {notes.get('next', 'No dispatch until readiness is verified')}",
    ]
    for key in ("completed", "decisions", "open_questions"):
        rows.append(f"\n## {key.replace('_', ' ').title()}")
        rows.extend(f"- {item}" for item in notes.get(key, []))
    rows.append("\n## Active ownership")
    for task, claim in data["claims"].items():
        observation = claim.get("observation") or {}
        rows.append(
            f"- {task}: {claim['owner']}; worktree={claim['repo']}; "
            f"paths={','.join(claim['paths'])}; "
            f"HEAD={observation.get('head', 'unobserved')}; "
            f"dirty={observation.get('dirty', 'unknown')}"
        )
    rows.append("\nReconcile Git, workers and uncertain effects before resuming.")
    return "\n".join(rows) + "\n"


def save(path, data):
    data["updated_at"] = now()
    data["revision"] = data.get("revision", 0) + 1
    atomic_json(path, data)
    # The projection is rebuildable; run.json stays authoritative if this write fails.
    atomic_text(path.parent / "CHECKPOINT.md", projection(data))


def initialize(workspace, program, tracker, principles):
    if not SLUG.fullmatch(program or ""):
        raise StateError("program must be a lowercase slug")
    links = {}
    for key, value in (("tracker", tracker), ("principles", principles)):
        target = within(workspace, workspace / value)
        if not target.is_file():
            raise StateError(f"{key} file missing")
        links[key] = str(target.relative_to(workspace))
    if SECRET.search(json.dumps(links)):
        raise StateError("credential-like value refused")
    pointer = pointer_path(workspace)
    if pointer.exists():
        _, active = load(workspace)
        if active["program"] != program:
            raise StateError(
                "another program is active; reconcile it (release claims, then deactivate) before switching"
            )
    path = run_path(workspace, program)
    if path.exists():
        existing = read_json(path)
        validate_state(existing)
        if existing.get("version") != 1 or existing.get("program") != program:
            raise StateError("existing run is invalid")
        if any(existing.get(key) != value for key, value in links.items()):
            raise StateError("existing source links differ; reconcile before resuming")
    else:
        save(path, {"version": 1, "program": program, "claims": {}, "checkpoint": {}, **links})
    atomic_json(pointer, {"version": 1, "run": str(path.relative_to(workspace))})


def deactivate(workspace, program):
    _, data = load(workspace)
    if data["program"] != program:
        raise StateError("program mismatch; reconcile first")
    if data["claims"]:
        raise StateError("active claims remain; release them before deactivating")
    # Archive by rename: the pointer and run artifacts are preserved, never deleted.
    archive = state_dir(workspace) / f"inactive-{uuid.uuid4().hex}.json"
    os.replace(pointer_path(workspace), archive)


def repair(workspace, program):
    if not program or not SLUG.fullmatch(program):
        raise StateError("repair requires a program slug")
    path = run_path(workspace, program)
    if not path.is_file():
        raise StateError(f"no run state for program '{program}'")
    data = read_json(path)
    validate_state(data)
    if data["program"] != program:
        raise StateError("program mismatch")
    for key in ("tracker", "principles"):
        if not within(workspace, workspace / data[key]).is_file():
            raise StateError("source missing")
    pointer = pointer_path(workspace)
    if pointer.exists():
        try:
            _, active = load(workspace)
        except StateError:
            active = None
        if active and active["program"] != program:
            raise StateError("a different valid program is active; deactivate it first")
        shutil.copy2(pointer, pointer.with_name(f"before-repair-{uuid.uuid4().hex}.json"))
    atomic_json(pointer, {"version": 1, "run": str(path.relative_to(workspace))})


def claim(data, task, owner, repo, paths):
    if not task or not owner or len(task) > 128 or len(owner) > 128:
        raise StateError("task and owner must be short nonempty IDs")
    if SECRET.search(json.dumps([task, owner, list(paths)])):
        raise StateError("credential-like value refused")
    if task in data["claims"]:
        raise StateError("task already claimed; reconcile before reassignment")
    repo = repo.resolve()
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise StateError("repo must be the worktree root")
    common = git(repo, "rev-parse", "--git-common-dir")
    identity = str((repo / common).resolve())
    normalized = []
    for item in paths:
        if not item or not item.strip() or Path(item).is_absolute():
            raise StateError("claim needs explicit repo-relative paths, no globs")
        if any(char in item for char in "*?[]"):
            raise StateError("claim needs explicit repo-relative paths, no globs")
        path = (repo / item).resolve()
        if not path.is_relative_to(repo):
            raise StateError("claim escapes repository")
        relative = path.relative_to(repo)
        if str(relative) == ".":
            raise StateError("claim scope must be inside the repository")
        normalized.append(str(relative))
    if not normalized:
        raise StateError("claim needs file scopes")
    for old in data["claims"].values():
        if old["identity"] != identity:
            continue
        for item in normalized:
            for occupied in old["paths"]:
                claimed, held = Path(item), Path(occupied)
                if claimed.is_relative_to(held) or held.is_relative_to(claimed):
                    raise StateError("scope collides with an active claim")
    data["claims"][task] = {
        "owner": owner,
        "repo": str(repo),
        "identity": identity,
        "paths": normalized,
        "claimed_at": now(),
    }


def release(data, task, owner):
    old = data["claims"].get(task)
    if old is None or old["owner"] != owner:
        raise StateError("owner mismatch; reconcile before release")
    del data["claims"][task]


def validate_notes(notes):
    required = {"objective", "next", "completed", "decisions", "open_questions"}
    if not isinstance(notes, dict) or set(notes) != required:
        raise StateError("notes need exactly objective/next/completed/decisions/open_questions")
    for key in ("objective", "next"):
        if not isinstance(notes[key], str) or not 1 <= len(notes[key]) <= 500:
            raise StateError("objective/next must contain 1-500 characters")
    for key in ("completed", "decisions", "open_questions"):
        items = notes[key]
        if not isinstance(items, list) or len(items) > 8:
            raise StateError("checkpoint lists have at most eight items")
        if any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in items):
            raise StateError("checkpoint items must contain 1-500 characters")
    if SECRET.search(json.dumps(notes)):
        raise StateError("credential-like note refused; use a source reference")
    return notes


def snapshot(data):
    for item in data["claims"].values():
        try:
            observed = {
                "head": git(Path(item["repo"]), "rev-parse", "HEAD"),
                "dirty": bool(git(Path(item["repo"]), "status", "--porcelain")),
                "observed_at": now(),
            }
        except (StateError, subprocess.TimeoutExpired, OSError):
            observed = {"head": "unknown", "dirty": "unknown", "observed_at": now()}
        prior = item.get("observation")
        if (
            not isinstance(prior, dict)
            or prior.get("head") != observed["head"]
            or prior.get("dirty") != observed["dirty"]
        ):
            item["observation"] = observed


def refresh(workspace, notes=None):
    """Observe Git outside the lock; merge only unchanged claim identities."""
    _, observed = load(workspace)
    snapshot(observed)
    with locked(workspace):
        path, current = load(workspace)
        if current["program"] != observed["program"]:
            raise StateError("active program changed while observing")
        for task, item in observed["claims"].items():
            live = current["claims"].get(task)
            if live and all(live[key] == item[key] for key in ("owner", "repo", "claimed_at")):
                live["observation"] = item["observation"]
        if notes is not None:
            current["checkpoint"] = notes
        save(path, current)


def read_notes(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise StateError("checkpoint notes file missing or invalid") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["init", "claim", "release", "checkpoint", "snapshot", "status", "deactivate", "repair"],
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--program")
    parser.add_argument("--tracker")
    parser.add_argument("--principles")
    parser.add_argument("--task")
    parser.add_argument("--owner")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--paths", nargs="+")
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    needed = {
        "init": ("program", "tracker", "principles"),
        "claim": ("task", "owner", "repo", "paths"),
        "release": ("task", "owner"),
        "checkpoint": ("notes",),
        "deactivate": ("program",),
        "repair": ("program",),
    }
    if any(getattr(args, key) is None for key in needed.get(args.command, ())):
        parser.error("missing command arguments")
    try:
        if args.command == "status":
            _, data = load(root)
            print(projection(data), end="")
            return 0
        if args.command in ("checkpoint", "snapshot"):
            notes = validate_notes(read_notes(args.notes)) if args.command == "checkpoint" else None
            refresh(root, notes)
            print("Software Factory checkpoint refreshed.")
            return 0
        with locked(root):
            if args.command == "init":
                initialize(root, args.program, args.tracker, args.principles)
            elif args.command == "deactivate":
                deactivate(root, args.program)
            elif args.command == "repair":
                repair(root, args.program)
            else:
                path, data = load(root)
                if args.command == "claim":
                    claim(data, args.task, args.owner, args.repo, args.paths)
                elif args.command == "release":
                    release(data, args.task, args.owner)
                save(path, data)
        print("Software Factory state updated.")
        return 0
    except (StateError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
