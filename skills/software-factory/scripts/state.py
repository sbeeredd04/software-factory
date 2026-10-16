"""Local execution state for the Software Factory kernel.

Owns the active-program pointer, exclusive path claims and checkpoint notes
under a consumer project's `.software-factory/` directory. Standard library
only. It observes Git read-only and never calls models, the network or any
Git writer, and never dispatches work.

Bounds (the full contract lives in the skill's recovery reference):

- Claims record active ownership: release each claim when its work is done.
  New claims warn above CLAIM_WARN_THRESHOLD (50) and are refused at
  MAX_ACTIVE_CLAIMS (100); the refusal names `release` and `reconcile` as the
  way out. `reconcile` lists claims whose worktree or HEAD no longer resolves
  (exit 1 when any are listed); claims are never expired silently.
- `snapshot` observes Git once per distinct worktree, never once per claim,
  and no Git subprocess ever runs while the state lock is held.
- `run.json` stays under MAX_RUN_BYTES (256 KiB); oversized or malformed
  state is refused whole, never partially read. Released claims are pruned
  from the active document; the last HISTORY_LIMIT (16) releases are kept as
  compact history — longer history belongs in the board record or checkpoint.
- `runs/<program>/` holds only run.json, CHECKPOINT.md, notes/, briefs/,
  evidence/, evals/ and handoffs/. Text receipts only: no binaries, no
  symlinks, at most 1 MiB per artifact and 16 MiB across the run tree.
  Derived boards and status summaries are never stored there. `audit`
  reports usage against those budgets (exit 1 on violations) read-only.
- The configured principles file must exist and carry content: a missing,
  zero-byte or whitespace-only file is a blocked state refused with the
  path named. There is no built-in default and never a silent fallback.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
EVAL_RUN_ID = re.compile(
    r"^r-([0-9]{8}T[0-9]{6}Z)-(quick|epic|premerge|canary)(?:-[1-9][0-9]*)?$"
)
SECRET = re.compile(
    r"sk-ant-[\w-]+|gh[pousr]_[\w]+|-----BEGIN .*PRIVATE KEY-----|"
    r"\b(?:password|api_key|access_token|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
STATE_DIR = ".software-factory"
LOCK_WAIT_SECONDS = 5.0
CLAIM_WARN_THRESHOLD = 50
MAX_ACTIVE_CLAIMS = 100
HISTORY_LIMIT = 16
MAX_RUN_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
RUNS_BUDGET_BYTES = 16 * 1024 * 1024
RUN_LAYOUT_FILES = {"run.json", "CHECKPOINT.md"}
RUN_LAYOUT_DIRS = {"notes", "briefs", "evidence", "evals", "handoffs"}


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


def read_run(path):
    """Read a run document, refusing anything over the byte budget whole."""
    try:
        size = Path(path).stat().st_size
    except OSError as exc:
        raise StateError("missing or invalid state; reconcile before continuing") from exc
    if size > MAX_RUN_BYTES:
        raise StateError(
            f"run state exceeds the {MAX_RUN_BYTES}-byte budget; reconcile or archive before continuing"
        )
    return read_json(path)


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
    data = read_run(path)
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
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > HISTORY_LIMIT:
        raise StateError("invalid release history")
    for entry in history:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key]
            for key in ("task", "owner", "released_at")
        ):
            raise StateError("invalid release history")


def projection(data):
    notes = data.get("checkpoint") or {}
    rows = [
        f"# Software Factory checkpoint: {data['program']}",
        f"Updated: {data.get('updated_at', 'unknown')}",
        f"Planning source: {data['tracker']} (the tracker feeds planning; it is never a status store)",
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


def require_source_file(workspace, key, value):
    """Validate a configured source path; every refusal names the path.

    The principles file must carry real content: an empty (zero-byte or
    whitespace-only) file is a blocked state, refused with its path named
    and never replaced by a built-in default.
    """
    target = within(workspace, workspace / value)
    if not target.is_file():
        raise StateError(f"{key} file missing: {value}")
    if key == "principles":
        try:
            text = target.read_text(errors="replace")
        except OSError as exc:
            raise StateError(f"principles file unreadable: {value}") from exc
        if not text.strip():
            raise StateError(f"principles file empty: {value}")
    return target


def initialize(workspace, program, tracker, principles):
    if not SLUG.fullmatch(program or ""):
        raise StateError("program must be a lowercase slug")
    links = {}
    for key, value in (("tracker", tracker), ("principles", principles)):
        target = require_source_file(workspace, key, value)
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
        save(
            path,
            {"version": 1, "program": program, "claims": {}, "checkpoint": {}, "history": [], **links},
        )
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
    data = read_run(path)
    validate_state(data)
    if data["program"] != program:
        raise StateError("program mismatch")
    for key in ("tracker", "principles"):
        require_source_file(workspace, key, data[key])
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


def prepare_claim(repo, paths):
    """Resolve a claim's Git identity and scope; runs before the state lock."""
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
    return repo, identity, normalized


def claim(data, task, owner, repo, identity, normalized):
    if not task or not owner or len(task) > 128 or len(owner) > 128:
        raise StateError("task and owner must be short nonempty IDs")
    if SECRET.search(json.dumps([task, owner, list(normalized)])):
        raise StateError("credential-like value refused")
    if task in data["claims"]:
        raise StateError("task already claimed; reconcile before reassignment")
    if len(data["claims"]) >= MAX_ACTIVE_CLAIMS:
        raise StateError(
            f"active claim cap ({MAX_ACTIVE_CLAIMS}) reached; release finished claims "
            "or run reconcile to list stale ones"
        )
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
        "paths": list(normalized),
        "claimed_at": now(),
    }


def release(data, task, owner):
    old = data["claims"].get(task)
    if old is None or old["owner"] != owner:
        raise StateError("owner mismatch; reconcile before release")
    del data["claims"][task]
    # Released claims leave the active document; a bounded trail preserves history.
    history = data.setdefault("history", [])
    history.append({"task": task, "owner": owner, "released_at": now()})
    del history[:-HISTORY_LIMIT]


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
    """Observe Git once per distinct worktree, never once per claim."""
    observed_by_repo = {}
    stamp = now()
    for item in data["claims"].values():
        repo = item["repo"]
        if repo not in observed_by_repo:
            try:
                observed_by_repo[repo] = {
                    "head": git(Path(repo), "rev-parse", "HEAD"),
                    "dirty": bool(git(Path(repo), "status", "--porcelain")),
                }
            except (StateError, subprocess.TimeoutExpired, OSError):
                observed_by_repo[repo] = {"head": "unknown", "dirty": "unknown"}
        observed = observed_by_repo[repo]
        prior = item.get("observation")
        if (
            not isinstance(prior, dict)
            or prior.get("head") != observed["head"]
            or prior.get("dirty") != observed["dirty"]
        ):
            item["observation"] = {**observed, "observed_at": stamp}


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


def sanitize(value):
    """One printable line of a state value for terminal output."""
    return "".join(char for char in str(value) if char.isprintable())[:128]


def reconcile(workspace):
    """List claims whose worktree or HEAD no longer resolves; never releases."""
    _, data = load(workspace)
    resolved = {}
    stale = []
    for task, item in data["claims"].items():
        repo = item["repo"]
        if repo not in resolved:
            try:
                head = git(Path(repo), "rev-parse", "HEAD")
                resolved[repo] = bool(re.fullmatch(r"[0-9a-f]{40}", head))
            except (StateError, subprocess.TimeoutExpired, OSError):
                resolved[repo] = False
        if not resolved[repo]:
            stale.append((task, item))
    for task, item in stale:
        print(
            f"stale claim: task={sanitize(task)} owner={sanitize(item['owner'])} "
            f"worktree={sanitize(item['repo'])}"
        )
    if stale:
        print(
            f"{len(stale)} stale claim(s); release each with "
            "`state.py release --task <task> --owner <owner>` after confirming the owner"
        )
        print("claims are never expired silently")
        return 1
    print("no stale claims; every claimed worktree and HEAD resolves")
    return 0


def is_eval_run_id(name):
    """Recognize sf-eval receipt directories without relaxing program slugs."""
    match = EVAL_RUN_ID.fullmatch(name)
    if match:
        try:
            datetime.strptime(match[1], "%Y%m%dT%H%M%SZ")
            return True
        except ValueError:
            pass
    return False


def audit_runs(workspace, budget=RUNS_BUDGET_BYTES, artifact_limit=MAX_ARTIFACT_BYTES):
    """Measure the run tree against its layout and size budgets; read-only."""
    problems = []
    total = 0
    files = 0
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    def incomplete(relative):
        problems.append(f"incomplete measurement: cannot inspect runs/{sanitize(relative)}")

    def inspect(parent_fd, name, relative, info):
        nonlocal total, files
        label = sanitize(relative)
        is_dir = stat.S_ISDIR(info.st_mode)
        is_file = stat.S_ISREG(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            problems.append(f"symlink refused under runs/: {label}")
            return
        depth = len(relative.parts)
        if (depth == 0 and not is_dir) or (
            depth == 1 and (not is_dir or not (SLUG.fullmatch(name) or is_eval_run_id(name)))
        ) or (depth == 2 and not (
            (name in RUN_LAYOUT_FILES and is_file) or (name in RUN_LAYOUT_DIRS and is_dir)
        )):
            problems.append(f"undocumented entry under runs/: {label}")
        if not is_dir and not is_file:
            problems.append(f"unsupported entry under runs/: {label}")
            return
        if is_file:
            total += info.st_size
            files += 1
            if info.st_size > artifact_limit:
                problems.append(
                    f"artifact above the {artifact_limit}-byte limit under runs/: "
                    f"{label}; keep large artifacts in the project or external storage and link them"
                )
            if name == "run.json" and info.st_size > MAX_RUN_BYTES:
                problems.append(f"run.json above its {MAX_RUN_BYTES}-byte budget: {label}")
        flags = directory_flags if is_dir else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            descriptor = os.open(name, flags, dir_fd=parent_fd)
        except OSError:
            incomplete(relative)
            return
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_mode) != (
                info.st_dev, info.st_ino, info.st_mode
            ):
                incomplete(relative)
                return
            if is_file:
                if b"\0" in os.read(descriptor, 4096):
                    problems.append(f"binary content refused under runs/: {label}")
                return
            # Preserve entries already observed if directory iteration fails partway.
            entries = []
            try:
                with os.scandir(descriptor) as iterator:
                    entries.extend(iterator)
            except OSError:
                incomplete(relative)
            for entry in sorted(entries, key=lambda item: item.name):
                child = relative / entry.name
                try:
                    child_info = entry.stat(follow_symlinks=False)
                except OSError:
                    incomplete(child)
                    continue
                inspect(descriptor, entry.name, child, child_info)
        except OSError:
            incomplete(relative)
        finally:
            os.close(descriptor)

    try:
        state_fd = os.open(Path(workspace) / STATE_DIR, directory_flags)
    except FileNotFoundError:
        return total, files, problems
    except OSError:
        incomplete(" (state directory unavailable or symlinked)")
        return total, files, problems
    try:
        try:
            info = os.stat("runs", dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            return total, files, problems
        except OSError:
            incomplete("")
            return total, files, problems
        inspect(state_fd, "runs", Path(), info)
    finally:
        os.close(state_fd)
    if total > budget:
        problems.append(
            f"runs/ holds {total} bytes, above the {budget}-byte budget; "
            "move large artifacts to the project or external storage and link them"
        )
    return total, files, problems


def audit(workspace):
    """Report run-tree usage against the budgets; flags violations, never writes."""
    total, files, problems = audit_runs(workspace)
    print(
        f"runs/ usage: {total} bytes in {files} files "
        f"(budget {RUNS_BUDGET_BYTES} bytes, per-artifact limit {MAX_ARTIFACT_BYTES} bytes)"
    )
    for problem in problems:
        print(f"runs: {problem}", file=sys.stderr)
    if problems:
        print(
            "runs: reconcile the run tree against the documented layout and budgets",
            file=sys.stderr,
        )
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "init", "claim", "release", "checkpoint", "snapshot", "status",
            "reconcile", "audit", "deactivate", "repair",
        ],
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
        if args.command == "reconcile":
            return reconcile(root)
        if args.command == "audit":
            return audit(root)
        if args.command in ("checkpoint", "snapshot"):
            notes = validate_notes(read_notes(args.notes)) if args.command == "checkpoint" else None
            refresh(root, notes)
            print("Software Factory checkpoint refreshed.")
            return 0
        prepared = None
        if args.command == "claim":
            prepared = prepare_claim(args.repo, args.paths)  # Git runs before the lock.
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
                    claim(data, args.task, args.owner, *prepared)
                elif args.command == "release":
                    release(data, args.task, args.owner)
                save(path, data)
                if args.command == "claim" and len(data["claims"]) > CLAIM_WARN_THRESHOLD:
                    print(
                        f"state: warning: {len(data['claims'])} active claims "
                        f"(above {CLAIM_WARN_THRESHOLD}); release each claim when its work is done",
                        file=sys.stderr,
                    )
        print("Software Factory state updated.")
        return 0
    except (StateError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
