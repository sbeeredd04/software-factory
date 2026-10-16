"""Conservative uninstall transactions and read-only installation diagnostics.

Manifest entries are claims, not authority over arbitrary project files.
Only known projector destinations are eligible; doctor executes verified
adapter bytes in disposable fixtures, never configured shell commands.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import uuid
from contextlib import contextmanager
from pathlib import Path

DIGEST = re.compile(r"[0-9a-f]{64}\Z")
BACKUP_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\Z")
HOOK_FILES = {"claude-code": ".claude/settings.json", "cursor": ".cursor/hooks.json",
              "codex": ".codex/hooks.json"}


def safe_path(root, rel, api):
    """Reject even internal symlink aliases: deleting an alias is ambiguous."""
    if not isinstance(rel, str) or not rel or not rel.isprintable() or Path(rel).is_absolute():
        raise api.InstallError("unsafe installation path; reconcile the manifest manually")
    if Path(rel).as_posix() != rel or any(p in (".", "..") for p in rel.split("/")):
        raise api.InstallError("unsafe installation path; reconcile the manifest manually")
    current = root
    for part in Path(rel).parts:
        current /= part
        if current.is_symlink():
            raise api.InstallError("symlink in installation paths; reconcile manually")
    return current


def catalog(root, api):
    actions = []
    for host in api.REGISTERED_HOSTS:
        actions.extend(api.PROJECTORS[host](root, api.load_policy(host), "full"))
    actions.extend(api.project_shared_skills(list(api.REGISTERED_HOSTS)))
    return {a.path: a for a in actions}


def manifest(root, api):
    safe_path(root, api.MANIFEST_REL, api)
    safe_path(root, api.LOCK_REL, api)
    data = api.load_manifest(root)
    if data is None:
        return None, catalog(root, api)
    known = catalog(root, api)
    if (data.get("version") != 1 or not isinstance(data.get("pack"), dict)
            or data["pack"].get("name") != api.PACK_NAME
            or not isinstance(data.get("hosts"), list)
            or not data["hosts"] or any(not isinstance(h, str) for h in data["hosts"])
            or len(set(data["hosts"])) != len(data["hosts"])
            or any(h not in api.REGISTERED_HOSTS for h in data["hosts"])
            or data.get("profile") not in ("full", "skills-only")):
        raise api.InstallError("invalid installation ownership metadata; reconcile manually")
    seen = set()
    for entry in data["files"]:
        if not isinstance(entry, dict):
            raise api.InstallError("invalid installation file record; reconcile manually")
        rel = entry.get("path")
        safe_path(root, rel, api)
        action = known.get(rel)
        if (action is None or rel in seen or entry.get("action") != action.kind
                or entry.get("host") != action.host
                or (action.host is not None and action.host not in data["hosts"])
                or not isinstance(entry.get("sha256"), str)
                or not DIGEST.fullmatch(entry["sha256"])):
            raise api.InstallError("unsupported installation ownership record; reconcile manually")
        seen.add(rel)
        for backup in (entry.get("backup"), (entry.get("restore") or {}).get("path")
                       if isinstance(entry.get("restore"), dict) else None):
            if backup is not None:
                backup_path(root, backup, rel, api)
        if "restore" in entry and entry["restore"] is not None:
            restore = entry["restore"]
            if (not isinstance(restore, dict) or set(restore) != {"path", "sha256"}
                    or not isinstance(restore.get("sha256"), str)
                    or not DIGEST.fullmatch(restore["sha256"])):
                raise api.InstallError("invalid restoration receipt; reconcile manually")
    return data, known


def backup_path(root, backup, rel, api):
    path = safe_path(root, backup, api)
    parts = Path(backup).parts
    if (len(parts) < 4 or parts[:2] != (api.STATE_DIR, "backups")
            or not BACKUP_ID.fullmatch(parts[2]) or "/".join(parts[3:]) != rel):
        raise api.InstallError("invalid backup location; reconcile manually")
    return path


def read(root, rel, api, observed):
    content = api.read_file(safe_path(root, rel, api), rel)
    observed[rel] = content
    return content


def restored_bytes(root, entry, api, observed):
    receipt = entry.get("restore")
    if not isinstance(receipt, dict):
        return None
    path = backup_path(root, receipt["path"], entry["path"], api)
    content = read(root, path.relative_to(root).as_posix(), api, observed)
    if content is None or api.sha256(content) != receipt["sha256"]:
        raise api.InstallError("restoration backup is missing or changed; reconcile manually")
    return content


def hook_arguments(command, root, host, event, api, *, execution=True):
    """Recognize the generated adapter; shell text is never executed."""
    if not isinstance(command, str):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if argv[-1:] == ["2>&1"]:
        argv = argv[:-1]
    expected = [str(root / api.RUNTIME_REL / "hook.py"), "--host", host, "--event", event]
    if argv[1:] not in (expected, [*expected, "--workspace", str(root)]):
        return None
    if not execution:
        # Removal is structural, not execution approval. A different or no
        # longer installed Python can still be an unambiguous factory adapter.
        return argv if Path(argv[0]).is_absolute() and Path(argv[0]).name.startswith("python") else None
    try:
        return argv if Path(argv[0]).samefile(sys.executable) else None
    except OSError:
        return None


def remove_hooks(content, root, host, api):
    data = json.loads(content)
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("invalid hooks")
    events = api.CURSOR_HOOK_EVENTS if host == "cursor" else (
        (name, normalized) for name, _, normalized in api.HOOK_EVENTS
    )
    for event, normalized in events:
        if event not in hooks:
            continue
        entries = hooks[event]
        if not isinstance(entries, list):
            raise TypeError("invalid hooks")
        kept = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise TypeError("invalid hook entry")
            if host == "cursor":
                if not hook_arguments(entry.get("command"), root, host, normalized, api, execution=False):
                    kept.append(entry)
            else:
                if not isinstance(entry.get("hooks"), list):
                    raise ValueError("invalid hook group")
                handlers = [h for h in entry["hooks"] if not (
                    isinstance(h, dict)
                    and hook_arguments(h.get("command"), root, host, normalized, api, execution=False)
                )]
                if handlers or not entry["hooks"]:
                    kept.append({**entry, "hooks": handlers})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    return (json.dumps(data, indent=2) + "\n").encode()


def remove_block(content, api):
    text = content.decode()
    if api.BLOCK_BEGIN not in text and api.BLOCK_END not in text:
        return content
    pattern = re.compile(
        rf"(?m)^{re.escape(api.BLOCK_BEGIN)}\n.*?^{re.escape(api.BLOCK_END)}(?:\n|$)", re.DOTALL
    )
    if text.count(api.BLOCK_BEGIN) != 1 or text.count(api.BLOCK_END) != 1:
        raise ValueError("ambiguous block")
    cleaned, count = pattern.subn("", text)
    if count != 1:
        raise ValueError("ambiguous block")
    return cleaned.encode()


def plan_uninstall(root, hosts, api):
    previous, known = manifest(root, api)
    observed = {api.MANIFEST_REL: api.read_file(root / api.MANIFEST_REL, api.MANIFEST_REL)}
    if previous is None or not set(hosts).intersection(previous["hosts"]):
        return previous, observed, [], []
    remaining = [h for h in previous["hosts"] if h not in hosts]
    shared = {a.path: a for a in api.project_shared_skills(remaining)} if set(remaining) & {"cursor", "codex"} else {}
    full_remaining = any(e["host"] in remaining and e["action"] in ("merge", "block")
                         for e in previous["files"])
    retained, changes, messages = [], [], []
    for entry in previous["files"]:
        rel = entry["path"]
        action = known[rel]
        shared_skill = rel.startswith(".agents/skills/")
        needed = (action.host in remaining if action.host is not None else
                  rel in shared if shared_skill else
                  full_remaining if rel.startswith(api.RUNTIME_REL + "/") else bool(remaining))
        if needed and not shared_skill:
            retained.append(entry)
            continue
        before = read(root, rel, api, observed)
        if before is None:
            if needed:
                retained.append(entry)
                messages.append(f"retained missing {rel}; reinstall the remaining host")
            continue
        unchanged = api.sha256(before) == entry["sha256"]
        if needed:
            if not unchanged:
                retained.append(entry)
                messages.append(f"retained edited {rel}; reconcile remaining-host policy manually")
                continue
            # Removing a host is not an upgrade from the current pack sources.
            after = before
            if "cursor" not in remaining and rel.endswith("/SKILL.md"):
                lines = before.decode("utf-8").split("\n")
                closing = api.frontmatter_close(lines, rel)
                lines[1:closing] = [line for line in lines[1:closing]
                                    if line != "disable-model-invocation: true"]
                after = "\n".join(lines).encode()
            retained.append({**entry, "sha256": api.sha256(after)})
        elif not unchanged and action.kind == "write":
            messages.append(f"retained edited {rel}; remove or reconcile manually")
            continue
        elif action.kind == "gitignore":
            after = api.merge_gitignore(before)
            messages.append("retained .gitignore volatile factory entries; backups, runs and lock remain private")
        else:
            original = restored_bytes(root, entry, api, observed)
            if unchanged and original is not None:
                after = original
            elif unchanged and entry.get("restore", "unknown") is None:
                after = None
            elif action.kind == "merge":
                try:
                    after = remove_hooks(before, root, action.host, api)
                except (ValueError, TypeError, AttributeError):
                    messages.append(f"retained malformed {rel}; remove factory hooks manually")
                    continue
                if b"runtime/hook.py" in after:
                    messages.append(f"retained possible factory hook in {rel}; remove stale or ambiguous adapters manually")
                if entry.get("restore", "unknown") is None and json.loads(after) in ({}, {"version": 1}):
                    after = None
            elif action.kind == "block":
                try:
                    after = remove_block(before, api)
                except ValueError:
                    messages.append(f"retained ambiguous {rel}; remove factory block manually")
                    continue
                if not after and entry.get("restore", "unknown") is None:
                    after = None
            elif "restore" not in entry:
                messages.append(f"retained {rel}; legacy backup provenance unverified, restore manually")
                continue
            else:
                after = None
        if before != after:
            changes.append((rel, before, after))
            messages.append(f"{'remove' if after is None else 'update/restore'} {rel}")
    after_manifest = None
    if remaining:
        updated = {**previous, "hosts": remaining, "profile": "full" if full_remaining else "skills-only",
                   "files": sorted(retained, key=lambda e: e["path"])}
        after_manifest = (json.dumps(updated, indent=2) + "\n").encode()
    changes.append((api.MANIFEST_REL, observed[api.MANIFEST_REL], after_manifest))
    return previous, observed, changes, messages


@contextmanager
def parent_fd(root_fd, rel):
    """Anchor every component without following links, including during races."""
    fd = os.dup(root_fd)
    try:
        for part in Path(rel).parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd, Path(rel).name
    finally:
        os.close(fd)


def read_at(fd, name):
    try:
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(source, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise OSError("installation entry is not a regular file")
        return stream.read()


def recovery_directory(root_fd):
    """Private retained recovery copies also preserve writes through old fds."""
    state_fd = os.open(".software-factory", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=root_fd)
    try:
        try:
            os.mkdir("backups", 0o700, dir_fd=state_fd)
        except FileExistsError:
            pass
        backups_fd = os.open("backups", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=state_fd)
        try:
            name = "uninstall-" + uuid.uuid4().hex
            os.mkdir(name, 0o700, dir_fd=backups_fd)
            descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=backups_fd)
            return descriptor, f".software-factory/backups/{name}"
        finally:
            os.close(backups_fd)
    finally:
        os.close(state_fd)


def publish(fd, name, content, *, expected, quarantine, relative):
    """Capture then verify the actual entry; never replace a newly created name.

    Originals stay in private backups with receipts. An editor holding an old
    descriptor can still write after capture, so deleting these copies would
    discard unobserved edits. Recovery deliberately retains that evidence.
    """
    token = uuid.uuid4().hex
    captured = token + ".original"
    temporary = token + ".new"
    saved = False
    try:
        if expected is not None:
            receipt = json.dumps({"path": relative, "original": captured,
                                  "expected_sha256": hashlib.sha256(expected).hexdigest()}).encode()
            receipt_fd = os.open(token + ".json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=quarantine)
            with os.fdopen(receipt_fd, "wb") as stream:
                stream.write(receipt)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(name, captured, src_dir_fd=fd, dst_dir_fd=quarantine)
            saved = True
            if read_at(quarantine, captured) != expected:
                raise OSError("captured installation entry changed; reconcile recovery copies")
        if content is not None:
            stream_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=quarantine)
            with os.fdopen(stream_fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # link is an exclusive publication: concurrent replacement wins.
            os.link(temporary, name, src_dir_fd=quarantine, dst_dir_fd=fd,
                    follow_symlinks=False)
        elif read_at(fd, name) is not None:
            raise OSError("concurrent replacement retained; reconcile manually")
    except BaseException:
        if saved:
            try:
                os.link(captured, name, src_dir_fd=quarantine, dst_dir_fd=fd,
                        follow_symlinks=False)
            except FileExistsError:
                pass
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=quarantine)
        except FileNotFoundError:
            pass


def anchored_read(root_fd, rel):
    try:
        with parent_fd(root_fd, rel) as (fd, name):
            return read_at(fd, name)
    except FileNotFoundError:
        return None


def apply_uninstall(root, observed, changes, api):
    created = set()
    safe_path(root, api.LOCK_REL, api)
    lock_fd, _lock_path = api.acquire_lock(root, created)
    root_fd = None
    quarantine_fd = None
    applied = []
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for rel, before in observed.items():
            if anchored_read(root_fd, rel) != before:
                raise api.InstallError("installation or backup changed while planning; retry")
        quarantine_fd, quarantine_rel = recovery_directory(root_fd)
        try:
            for rel, before, after in changes:
                with parent_fd(root_fd, rel) as (fd, name):
                    if read_at(fd, name) != before:
                        raise api.InstallError("installation changed while uninstalling; retry")
                    parent = os.fstat(fd)
                    applied.append((rel, before, after, (parent.st_dev, parent.st_ino)))
                    publish(fd, name, after, expected=before, quarantine=quarantine_fd, relative=rel)
        except BaseException:
            for rel, before, after, identity in reversed(applied):
                try:
                    with parent_fd(root_fd, rel) as (fd, name):
                        parent = os.fstat(fd)
                        current = read_at(fd, name)
                        if (parent.st_dev, parent.st_ino) != identity:
                            raise OSError("concurrent edit")
                        if current == before:
                            continue  # Publication failed before changing this entry.
                        if current != after:
                            raise OSError("concurrent edit")
                        publish(fd, name, before, expected=after, quarantine=quarantine_fd, relative=rel)
                except OSError:
                    # One contested entry must not prevent independent recovery.
                    print(f"uninstall: retained contested {rel}; reconcile manually", file=sys.stderr)
            raise
        # Only empty ancestors of removed owned payloads, through anchored fds.
        dirs = set()
        for rel, _, after in changes:
            if after is not None or not any(rel.startswith(prefix) for prefix in (
                ".claude/skills/", ".claude/agents/", ".cursor/agents/", ".codex/agents/",
                ".agents/skills/", api.RUNTIME_REL + "/",
            )):
                continue
            parent = Path(rel).parent
            while len(parent.parts) >= 2:
                dirs.add(parent.as_posix())
                parent = parent.parent
        for directory in sorted(dirs, key=lambda p: -len(Path(p).parts)):
            try:
                with parent_fd(root_fd, directory) as (fd, name):
                    os.rmdir(name, dir_fd=fd)
            except OSError:
                pass
    finally:
        if quarantine_fd is not None:
            os.close(quarantine_fd)
            print(f"uninstall: recovery copies and receipts retained under {quarantine_rel}; inspect them for concurrent edits")
        if root_fd is not None:
            os.close(root_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        # The shared installation lock retains its inode for waiting writers.


def uninstall(args, api):
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        raise api.InstallError("project directory is missing")
    if args.host == "auto":
        raise api.InstallError("uninstall requires explicit hosts or all")
    hosts = api.resolve_hosts(args.host, root)
    _, observed, changes, messages = plan_uninstall(root, hosts, api)
    for message in messages:
        print(f"uninstall: {message}")
    if args.dry_run:
        print(f"uninstall: dry-run; {len(changes)} planned changes; nothing written")
    elif changes:
        try:
            apply_uninstall(root, observed, changes, api)
        except OSError as exc:
            raise api.InstallError("uninstall failed; inspect recovery before retrying") from exc
        print(f"uninstall: {len(changes)} changes applied; user state and backups retained")
    else:
        print("uninstall: 0 changes; no selected installation")
    return 0


def hook_fixture(root, host, entries, api):
    """Exercise a copied, verified adapter, never mutable configured shell text."""
    owned = {e["path"]: e for e in entries}
    payloads = {}
    for name in api.RUNTIME_HELPERS:
        rel = f"{api.RUNTIME_REL}/{name}"
        path = safe_path(root, rel, api)
        if rel not in owned or not path.is_file():
            return "warning", "runtime ownership incomplete; reinstall before hook verification"
        content = path.read_bytes()
        canonical = (api.PACK_ROOT / api.KERNEL_SCRIPTS / name).read_bytes()
        if content != canonical or api.sha256(content) != owned[rel]["sha256"]:
            return "warning", f"{rel} differs from trusted source; no hook code executed"
        payloads[name] = content
    # stdin/cwd/state always belong to a disposable fixture, including PreCompact.
    with tempfile.TemporaryDirectory(prefix="sf-doctor-") as temp:
        fixture = Path(temp)
        runtime = fixture / api.RUNTIME_REL
        runtime.mkdir(parents=True)
        for name, content in payloads.items():
            (runtime / name).write_bytes(content)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("CURSOR_VERSION", None)
        env.pop("CURSOR_PROJECT_DIR", None)
        base = [sys.executable, "-I", "-B", str(runtime / "hook.py"), "--host", host]

        def run(event):
            return subprocess.run(
                [*base, "--event", event, "--workspace", str(fixture)],
                input='{"session_id":"doctor-fixture","is_background_agent":false}',
                text=True, capture_output=True, cwd=fixture, env=env, timeout=10, check=False,
            )

        inert = run("session-start")
        if (inert.returncode, inert.stdout, inert.stderr) != (0, "", ""):
            return "warning", "hook fixture failed inertness; inspect the installation"
        run_dir = fixture / api.STATE_DIR / "runs/doctor"
        run_dir.mkdir(parents=True)
        state = {"version": 1, "program": "doctor", "tracker": "tracker.yaml",
                 "principles": "principles.md", "claims": {}, "checkpoint": {}, "revision": 1}
        (run_dir / "run.json").write_text(json.dumps(state))
        (fixture / api.STATE_DIR / "active.json").write_text(json.dumps({
            "version": 1, "run": f"{api.STATE_DIR}/runs/doctor/run.json",
        }))
        active = run("session-start")
        context = json.loads(active.stdout)
        if host == "cursor":
            valid = set(context) == {"additional_context"}
            pointer = context.get("additional_context")
        else:
            inner = context.get("hookSpecificOutput", {})
            valid = (set(context) == {"hookSpecificOutput"}
                     and set(inner) == {"hookEventName", "additionalContext"}
                     and inner.get("hookEventName") == "SessionStart")
            pointer = inner.get("additionalContext")
        if (active.returncode or active.stderr or not valid or not isinstance(pointer, str)
                or not 0 < len(pointer) <= 1500 or "not a new authorization" not in pointer):
            return "warning", "hook fixture returned an unexpected envelope"
        compact = run("pre-compact")
        snapshot = json.loads((run_dir / "run.json").read_text())
        if (compact.returncode, compact.stdout, compact.stderr) != (0, "", "") or snapshot["revision"] <= 1:
            return "warning", "pre-compact fixture did not refresh safely"
    return "pass", "verified installed adapter bytes passed disposable fixtures; live host loading unverified"


def permission_findings(value):
    """Only fixed setting labels leave this scanner; values never do."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("approval_policy", "ask_for_approval") and item == "never":
                found.add("approval_policy=never")
            if key == "sandbox_mode" and item == "danger-full-access":
                found.add("sandbox_mode=danger-full-access")
            found.update(permission_findings(item))
    elif isinstance(value, list):
        for item in value:
            found.update(permission_findings(item))
    elif isinstance(value, str):
        for marker in ("bypassPermissions", "--dangerously-skip-permissions",
                       "--dangerously-bypass-approvals-and-sandbox", "--yolo"):
            if marker in value:
                found.add(marker)
    return found


def trusted_module(name, api):
    # Doctor must leave even a fresh source checkout free of bytecode writes.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        f"sf_doctor_{name}", api.PACK_ROOT / api.KERNEL_SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe_work(root, api, add):
    state = trusted_module("state", api)
    total, files, problems = state.audit_runs(root)
    categories = []
    for label, markers in (
        ("layout", ("undocumented", "symlink", "unsupported")),
        ("size budget", ("above",)), ("binary", ("binary",)),
        ("incomplete measurement", ("incomplete",)),
    ):
        if any(any(marker in problem for marker in markers) for problem in problems):
            categories.append(label)
    add("runs-audit", "warning" if problems else "pass",
        f"read-only observation: {files} files, {total} bytes; budget {state.RUNS_BUDGET_BYTES} bytes; "
        + ("findings: " + ", ".join(categories) + "; run state.py audit to reconcile locally"
           if problems else "no layout, size-budget or binary findings"))
    roadmap = trusted_module("roadmap", api)
    roadmap._STATE = state
    try:
        safe_path(root, roadmap.CONFIG_FILE, api)
        config = roadmap.board_config(root)
        directory = safe_path(root, config["dir"], api)
        if not directory.exists():
            add("board-records", "unverified", "no board records; initialize the board when planning; per-story records own live status")
            return
        for path in directory.rglob("*"):
            safe_path(root, path.relative_to(root).as_posix(), api)
        payload = roadmap.compute_roadmap(root, config, directory)
        add("board-records", "warning" if payload["problems"] else "pass",
            f"per-story records own live status; {len(payload['stories'])} stories observed; "
            f"{len(payload['problems'])} consistency findings; no records changed")
        expected = {"version": 1, "generated": {
            "by": roadmap.GENERATED_BY, "command": roadmap.GENERATED_COMMAND,
            "note": roadmap.GENERATED_NOTE,
        }, **payload}
        document = None
        try:
            document = json.loads((directory / "roadmap.json").read_text())
            if not isinstance(document, dict):
                raise TypeError("invalid projection")
            actual = {key: value for key, value in document.items()
                      if key not in ("revision", "generated_at")}
            fresh = actual == expected
        except (OSError, ValueError, TypeError):
            fresh = False
        add("board-roadmap", "pass" if fresh else "warning",
            "roadmap.json matches board records" if fresh else
            "roadmap.json missing, invalid or stale; regenerate with roadmap.py build; doctor does not repair projections")
        try:
            html = (directory / "dashboard.html").read_text()
            fresh_html = fresh and html == roadmap.dashboard_module().render_html(document)
        except (OSError, ValueError, KeyError, TypeError):
            fresh_html = False
        add("board-dashboard", "pass" if fresh_html else "warning",
            "dashboard.html matches board records" if fresh_html else
            "dashboard.html missing or stale; regenerate with roadmap.py build; doctor does not repair projections")
    except (api.InstallError, OSError, ValueError, TypeError, KeyError, AttributeError):
        add("board-records", "warning", "board configuration or records are unreadable or inconsistent; reconcile source records; no projections repaired")


def observe_source(root, path, key, api, add):
    label = "configured source path"
    try:
        safe_path(root, path, api)
        # Values may contain credentials; emit only ordinary relative paths.
        if re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", path) and not re.search(
            r"gh[pousr]_|github_pat_|sk-|AKIA", path
        ):
            label = path
        trusted_module("state", api).require_source_file(root, key, path)
        add(key, "pass", f"{label} satisfies source-file requirements; content agreement remains a human judgment")
    except (api.InstallError, OSError, ValueError, TypeError):
        add(key, "blocked", f"{label} is missing, empty or unreadable; supply the configured source; no fallback applied")


def doctor(args, api):
    root = args.project.expanduser().resolve()
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    try:
        data, _known = manifest(root, api)
    except (api.InstallError, OSError, ValueError, TypeError, AttributeError):
        data = None
        add("installation", "blocked", "installation ownership is unsafe or malformed; reconcile manually")
    if data is None:
        if not checks:
            add("installation", "blocked", "no installation; run install.py install --project PROJECT --host HOST")
    else:
        add("installation", "pass", "ownership records name supported projection destinations")
        owned = {entry["path"]: entry for entry in data["files"]}
        for rel, entry in owned.items():
            if isinstance(entry.get("restore"), dict):
                try:
                    restored_bytes(root, entry, api, {})
                except (api.InstallError, OSError):
                    add(f"backup:{rel}", "warning", f"{rel} original restoration backup is missing or changed; reconcile manually")
            try:
                content = api.read_file(safe_path(root, rel, api), rel)
                if content is None or api.sha256(content) != entry["sha256"]:
                    add(f"projection:{rel}", "warning", f"{rel} missing or hash mismatch; reconcile or reinstall")
            except (api.InstallError, OSError):
                add(f"projection:{rel}", "warning", f"{rel} cannot be inspected safely")
        for host in data["hosts"]:
            rel = HOOK_FILES[host]
            if rel not in owned:
                add(f"hooks:{host}", "unverified", "skills-only scope has no owned hook wiring")
                continue
            try:
                doc = json.loads(safe_path(root, rel, api).read_text())
                hooks = doc["hooks"]
                events = api.CURSOR_HOOK_EVENTS if host == "cursor" else (
                    (name, normalized) for name, _, normalized in api.HOOK_EVENTS
                )
                for event, normalized in events:
                    entries = hooks[event]
                    handlers = entries if host == "cursor" else [h for g in entries for h in g["hooks"]]
                    candidates = [h for h in handlers if isinstance(h, dict)
                                  and hook_arguments(h.get("command"), root, host, normalized, api, execution=False)]
                    if len(candidates) != 1:
                        raise ValueError("unexpected wiring")
                    argv = hook_arguments(candidates[0]["command"], root, host, normalized, api)
                    if argv is None:
                        raise ValueError("interpreter not established")
                status, detail = hook_fixture(root, host, data["files"], api)
                add(f"hooks:{host}", status, detail)
            except (api.InstallError, OSError, ValueError, TypeError, KeyError, AttributeError,
                    subprocess.TimeoutExpired):
                add(f"hooks:{host}", "warning", "hook wiring is unsafe, stale, or invalid; reinstall; no configured shell text executed")
        if "codex" in data["hosts"]:
            add("codex-hook-trust", "unverified", "user-confirmation-required: review and trust hooks through /hooks")
            add("codex-agent-permissions", "warning", "custom agents inherit parent permissions; role instructions and sandbox_mode do not enforce read-only isolation")
            add("codex-agent-loading", "unverified", "live custom-agent loading was not observed")
            if "cursor" in data["hosts"]:
                add("shared-skill-loading", "unverified", "Codex tolerance of Cursor frontmatter and combined live loading were not observed")
        for host in data["hosts"]:
            detector = api.PLUGIN_DETECTORS.get(host)
            if detector and detector(root):
                add(f"project-plugin:{host}", "warning", "project plugin marker and projection coexist; review installation alternatives")
    # Read only named project settings, never recurse into home or execute hooks.
    for rel in (*HOOK_FILES.values(), ".codex/config.toml"):
        try:
            path = safe_path(root, rel, api)
            if not path.is_file():
                continue
            content = path.read_text()
            doc = tomllib.loads(content) if rel.endswith(".toml") else json.loads(content)
            for setting in sorted(permission_findings(doc)):
                add(f"permissions:{rel}:{setting}", "blocked", f"{rel} contains {setting}; review the existing permission setting manually")
        except (api.InstallError, OSError, ValueError):
            add(f"settings:{rel}", "warning", f"{rel} is unreadable or malformed; settings were not partially interpreted")
    if data:
        try:
            pointer = safe_path(root, ".software-factory/active.json", api)
            if pointer.exists():
                active = json.loads(pointer.read_text())
                run_rel = active.get("run")
                if active.get("version") != 1 or not isinstance(run_rel, str) or not re.fullmatch(
                    r"\.software-factory/runs/[a-z0-9][a-z0-9-]{0,63}/run\.json", run_rel
                ):
                    raise ValueError("invalid pointer")
                run = json.loads(safe_path(root, run_rel, api).read_text())
                if (run.get("version") != 1 or not isinstance(run.get("claims"), dict)
                        or not isinstance(run.get("checkpoint"), dict)
                        or not all(isinstance(run.get(key), str) and run[key]
                                   for key in ("program", "tracker", "principles"))):
                    raise ValueError("invalid run")
                for source_key in ("principles", "tracker"):
                    observe_source(root, run[source_key], source_key, api, add)
                add("recovery-state", "unverified", "recovery documents parse; full state semantics and live recovery require reconciliation")
        except (api.InstallError, OSError, ValueError, AttributeError, TypeError):
            add("recovery-state", "warning", "recovery state could not be read; reconcile manually; no actual run was refreshed")
    observe_work(root, api, add)
    if (root / ".claude/skills").is_dir() and (root / ".agents/skills").is_dir():
        add("ambient-skill-sources", "warning", "duplicate ambient sources at .claude/skills and .agents/skills; review host discovery")
    add("global-plugin-state", "unverified", "global plugin configuration was not observed; project checks cannot establish absence of duplicates")
    validator = trusted_module("config", api)
    try:
        path = safe_path(root, ".software-factory/config.yaml", api)
        if not path.is_file():
            add("config-syntax", "unverified", "config.yaml is absent; complete project configuration")
            add("config-semantics", "unverified", "setup required; no configuration policy established")
        else:
            validator.load(path)
            add("config-syntax", "pass", "config.yaml parses in the JSON-compatible YAML subset")
            try:
                validator.validate_file(path, root=root)
                add("config-semantics", "pass", "schema and semantic references validated; declarations do not establish live authority")
            except validator.ConfigError as exc:
                add("config-semantics", "blocked", str(exc))
    except (api.InstallError, OSError, ValueError):
        add("config-syntax", "blocked", "config.yaml is outside the supported JSON-compatible YAML subset or unreadable; no partial interpretation")
        add("config-semantics", "unverified", "syntax must be repaired before semantic validation")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("sf_doctor_bmad", api.PACK_ROOT / "scripts/bmad_install.py")
    bmad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bmad)
    observed, parsed = bmad.observe(root)
    previous = data.get("bmad", {}) if data else {}
    if not isinstance(previous, dict):
        previous = {}
    if parsed:
        expected = previous.get("manifest_sha256")
        changed = (expected is not None and expected != observed["manifest_sha256"]) or previous.get("status") == "failed"
        add("bmad", "warning" if changed else "pass",
            "BMad identity changed or prior attempt failed; reconcile preserved installation; no repair performed" if changed else
            "BMad manifest observed with digest; installed declarations do not prove workflow compatibility")
    elif bmad.discovered(root) or previous.get("status") in ("failed", "installed", "existing"):
        add("bmad", "warning", "BMad artifacts are partial or unreadable; preserve and reconcile manually; native planning remains available")
    else:
        add("bmad", "unverified", "optional BMad is absent; native planning remains available; no provisioning attempted")
    gh = shutil.which("gh")
    if not gh:
        add("github-auth", "warning", "gh is unavailable; install and authenticate it for integration checks")
    else:
        try:
            result = subprocess.run([gh, "auth", "status"], capture_output=True, timeout=10, check=False)
            add("github-auth", "pass" if result.returncode == 0 else "warning",
                "gh auth status succeeded" if result.returncode == 0 else "gh authentication was not established; run gh auth login")
        except (OSError, subprocess.TimeoutExpired):
            add("github-auth", "warning", "gh auth status could not complete; check authentication manually")
    if args.json:
        print(json.dumps({"checks": checks}, indent=2))
    else:
        for check in checks:
            print(f"{check['status']}: {check['name']}: {check['detail']}")
    return int(any(check["status"] == "blocked" for check in checks))
