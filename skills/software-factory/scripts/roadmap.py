"""The Software Factory board kernel: per-story records and the roadmap projection.

The records under `.software-factory/context/board/` (`streams.json`,
`meta.json`, `epics/<id>.json`, `stories/<id>.json`) are the single live
story-status store. `roadmap.json` and `dashboard.html` are locked,
revision-stamped, fully regenerable projections of those records plus a
read-only mirror of live claims; `state.py` claims remain the
path-exclusivity system of record and are never written from here.

Ids are integers assigned once and never reused (the counters live in
`meta.json`); joins are by id, never by filename; build order is the explicit
`order` array, separate from ids. `derive` fails closed before minting: a
counter that does not exceed every existing record id, or that would mint an
id colliding with an existing record file, is refused with nothing written —
repairing a stale counter is an explicit operator edit, never an implicit
overwrite. Unknown record keys are ignored at read
time so receipts and project-specific fields extend the schema without code
changes. The normative record contract is the shipped
`schemas/board.schema.json`.

Ownership is enforced in code: workers self-serve `in-progress` / `in-review`
/ `blocked` and receipts on the story they hold a live claim for; the
orchestrator owns `ready-for-dev`, `built`, `done` and structural edits;
humans confirm cancellations and accept epics; `done` and `cancelled`
records are frozen history. Standard library only; never calls a model, an
agent CLI, Git or the network.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

_STATE = None
_DASHBOARD = None
_GATE = None
_UNSET = object()

DEFAULT_BOARD_DIR = ".software-factory/context/board"
CONFIG_FILE = ".software-factory/config.yaml"
BOARD_LOCK = "board.lock"
STATUSES = ["backlog", "ready-for-dev", "in-progress", "in-review", "built", "done", "cancelled"]
EPIC_STATUSES = ["planned", "in-progress", "awaiting-acceptance", "done", "parked", "cancelled"]
BLOCKED_TYPES = ["human-decision", "external", "resource-contention", "design"]
MET_STATUSES = {"in-review", "built", "done"}  # review counts as met for readiness
TERMINAL = {"done", "cancelled"}
GENERATED_BY = "roadmap.py build"
GENERATED_COMMAND = "python3 scripts/roadmap.py build --workspace <project-root>"
GENERATED_NOTE = (
    "Locked projection: do not hand-edit; regenerate it from the board records "
    f"with `{GENERATED_COMMAND}`."
)


class BoardError(ValueError):
    pass


def state_module():
    """Load the sibling state helper for its primitives; never its writers."""
    global _STATE
    if _STATE is None:
        spec = importlib.util.spec_from_file_location(
            "sf_state_helper", Path(__file__).resolve().with_name("state.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _STATE = module
    return _STATE


def dashboard_module():
    """Load the sibling dashboard renderer; the pack ships these together."""
    global _DASHBOARD
    if _DASHBOARD is None:
        spec = importlib.util.spec_from_file_location(
            "sf_dashboard_helper", Path(__file__).resolve().with_name("dashboard.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _DASHBOARD = module
    return _DASHBOARD


def now():
    return state_module().now()


def gate_module():
    global _GATE
    if _GATE is None:
        spec = importlib.util.spec_from_file_location(
            "sf_board_gate", Path(__file__).resolve().with_name("gate.py")
        )
        _GATE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_GATE)
    return _GATE


def scope_digest(record):
    """Stable approved story scope; progress and evidence do not redefine it."""
    scope = {key: record.get(key) for key in (
        "id", "epic", "source_key", "title", "type", "after", "covers", "scope", "risk",
        "hitl", "plan_checkpoint", "done_checkpoint",
    )}
    return gate_module().digest(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode())


def protected_configuration(workspace):
    try:
        return gate_module().strict_json(gate_module().bound_read(workspace, CONFIG_FILE))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as exc:
        raise BoardError("protected transition configuration is unsafe, malformed or over budget") from exc


def transition_config(workspace, args):
    protected = (args.command == "update" and args.actor == "orchestrator"
                 and args.status in ("ready-for-dev", "built", "done")) or (
                     args.command == "epic" and args.actor == "human" and args.status == "done")
    if not protected:
        return board_config(workspace)
    data = protected_configuration(workspace)
    args._strict_config_data = data
    args._validated_config = board_config(workspace, parsed_data=data)
    return args._validated_config


def required_checkpoint(workspace, record, args, phase, sha=None, *, use_argument=True):
    """Reuse a valid scoped decision; never treat --actor as authentication."""
    saved = record.get("checkpoint_decisions", {}).get(phase, {})
    if not isinstance(saved, dict):
        raise BoardError(f"{phase} checkpoint decision record is malformed")
    supplied = args.decision if use_argument else None
    path = supplied or saved.get("path")
    gate = gate_module()
    try:
        content = gate.bound_read(workspace, path)
        expected = gate.digest(content) if supplied else saved.get("sha256")
        gate.decision(workspace, path, expected, scope={"story": record["id"]},
                      phase=phase, sha=sha, scope_digest=scope_digest(record))
    except (OSError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise BoardError(f"{phase} checkpoint needs a current source-linked scoped approval") from exc
    if saved and saved != {"path": path, "sha256": expected}:
        record.setdefault("checkpoint_history", []).append({"phase": phase, **saved})
    record.setdefault("checkpoint_decisions", {})[phase] = {"path": path, "sha256": expected}


def protected_gate(workspace, record, args, phase):
    gate = gate_module()
    sha = args.sha
    if not isinstance(sha, str) or not gate.SHA1.fullmatch(sha):
        raise BoardError(f"{phase} needs --sha with the full current subject SHA")
    if phase == "premerge" and record.get("review_subject_sha") != sha:
        raise BoardError("premerge SHA does not match the current review subject; submit a fresh review")
    if not args.evidence:
        raise BoardError(f"{phase} requires --evidence <workspace-relative gate manifest>")
    try:
        content = gate.bound_read(workspace, args.evidence)
        report = gate.strict_json(content)
        # Board manifests use workspace-relative artifact/decision paths; every
        # read starts at the same pinned root, including intermediate parents.
        root = workspace
        config_data = getattr(args, "_strict_config_data", _UNSET)
        if config_data is _UNSET:
            config_data = protected_configuration(workspace)
        required = list(gate.DEFAULT_REQUIRED[phase])
        if config_data is not None and "verification" in config_data:
            required = gate.required_from_data(config_data, phase)
        built = record.get("accepted_gates", {}).get("premerge")
        accepted_checks = None
        if phase == "complete":
            if not isinstance(built, dict) or not isinstance(built.get("checks"), dict) or not built["checks"]:
                raise ValueError("complete requires accepted premerge obligations")
            accepted_checks = built["checks"]
            required = list(dict.fromkeys([*accepted_checks, *required]))
        errors = gate.validate_bound(report, root, sha, phase, required,
                                     scope={"story": record["id"]}, scope_digest=scope_digest(record))
        if errors:
            raise ValueError("; ".join(errors))
        if report.get("author") != record.get("owner"):
            raise ValueError("gate author does not match the story's implementation owner")
        if phase == "complete":
            if not isinstance(built, dict) or report.get("candidate_sha") != built.get("subject_sha"):
                raise ValueError("integration must cite the accepted candidate SHA")
            if record.get("review_subject_sha") != built["subject_sha"]:
                raise ValueError("current review subject changed after premerge acceptance")
            accepted = gate.bound_read(workspace, built.get("path"))
            if gate.digest(accepted) != built.get("sha256"):
                raise ValueError("accepted premerge manifest changed")
            prior_required = (gate.required_from_data(config_data, "premerge")
                              if config_data is not None and "verification" in config_data
                              else list(gate.DEFAULT_REQUIRED["premerge"]))
            prior_required = list(dict.fromkeys([*accepted_checks, *prior_required]))
            prior_report = gate.strict_json(accepted)
            if any(prior_report.get("checks", {}).get(name) != check for name, check in accepted_checks.items()):
                raise ValueError("accepted premerge obligations contradict their manifest")
            prior_errors = gate.validate_bound(prior_report, workspace, built["subject_sha"],
                                               "premerge", prior_required,
                                               scope={"story": record["id"]}, scope_digest=scope_digest(record))
            if prior_errors:
                raise ValueError("accepted premerge evidence changed: " + "; ".join(prior_errors))
            if record["plan_checkpoint"]:
                required_checkpoint(workspace, record, args, "plan", built["subject_sha"], use_argument=False)
            integration = report.get("integration")
            if (not isinstance(integration, dict) or integration.get("status") != "pass"
                    or integration.get("subject_sha") != sha
                    or integration.get("candidate_sha") != built["subject_sha"]):
                raise ValueError("integration outcome is missing, stale or unobserved")
            effect = report["checks"].get("deploy", {})
            if effect.get("status") != "pass" or not all(isinstance(effect.get(key), str) and effect[key].strip()
                       for key in ("artifact_id", "environment")):
                raise ValueError("complete evidence needs effect artifact and environment identities")
        if record["plan_checkpoint"] and phase == "premerge":
            required_checkpoint(workspace, record, args, "plan", sha)
        if phase == "complete" and (record["hitl"] or record["done_checkpoint"]):
            required_checkpoint(workspace, record, args, "complete", sha)
        binding = {"path": args.evidence, "sha256": gate.digest(content), "subject_sha": sha,
                   "phase": phase, "author": report["author"], "reviewer": report["reviewer"],
                   "checks": {name: report["checks"][name] for name in required}}
        record.setdefault("accepted_gates", {})[phase] = binding
        record["evidence_contract"] = 1
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError) as exc:
        raise BoardError(f"{phase} gate refused: {exc}") from exc


def epic_review_scope(workspace, config, record):
    """Bind exact current child records and the declared epic outcome."""
    gate = gate_module()
    directory = board_dir(workspace, config)
    _, _, epics, stories, problems = load_board(directory)
    if problems:
        raise BoardError("epic acceptance requires a readable consistent board")
    children = sorted((story for story in stories.values() if story["epic"] == record["id"]), key=lambda s: s["id"])
    if len(children) > 256 or len(record["needs"]) > 256:
        raise BoardError("epic review exceeds the 256-child/provider evidence budget; reconcile its scope")
    if len(record["order"]) != len(children) or set(record["order"]) != {story["id"] for story in children}:
        raise BoardError("epic child membership changed; reconcile the explicit order before acceptance")
    scope = {"epic": {key: record.get(key) for key in (
        "id", "title", "outcome", "done_when", "covers", "order", "needs", "source_key",
    )}, "children": [], "providers": []}
    measured = 0
    for kind, records in (("children", children), ("providers", [epics.get(i) for i in record["needs"]])):
        for item in records:
            if item is None:
                raise BoardError("epic acceptance has an unknown prerequisite")
            path = directory / ("stories" if kind == "children" else "epics") / f"{item['id']}.json"
            content = gate.bound_read(workspace, path.relative_to(workspace).as_posix())
            measured += len(content)
            if measured > gate.MAX_BOUND_ARTIFACT_BYTES:
                raise BoardError("epic scope reads exceeded the aggregate byte budget")
            if gate.strict_json(content) != item:
                raise BoardError("epic review sources changed while reading; retry")
            scope[kind].append({"id": item["id"], "sha256": gate.digest(content)})
    digest = gate.digest(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode())
    return digest, children, epics


def validate_child_acceptance(workspace, child, config_data):
    gate = gate_module()
    accepted = child.get("accepted_gates", {})
    for phase in ("premerge", "complete"):
        binding = accepted.get(phase)
        if not isinstance(binding, dict) or not isinstance(binding.get("checks"), dict):
            raise TypeError("protected child has missing acceptance evidence")
        content = gate.bound_read(workspace, binding.get("path"))
        if gate.digest(content) != binding.get("sha256"):
            raise ValueError("child acceptance manifest changed")
        report = gate.strict_json(content)
        required = (gate.required_from_data(config_data, phase)
                    if config_data is not None and "verification" in config_data
                    else list(gate.DEFAULT_REQUIRED[phase]))
        required = list(dict.fromkeys([*binding["checks"], *required]))
        if any(report.get("checks", {}).get(name) != check for name, check in binding["checks"].items()):
            raise ValueError("child acceptance obligations changed")
        errors = gate.validate_bound(report, workspace, binding["subject_sha"], phase, required,
                                     scope={"story": child["id"]}, scope_digest=scope_digest(child))
        if errors or report.get("author") != child.get("owner"):
            raise ValueError("child gate no longer passes")
        if phase == "complete":
            candidate = accepted.get("premerge", {}).get("subject_sha")
            integration = report.get("integration", {})
            effect = report["checks"].get("deploy", {})
            if (report.get("candidate_sha") != candidate or integration.get("candidate_sha") != candidate
                    or integration.get("status") != "pass" or integration.get("subject_sha") != binding["subject_sha"]
                    or effect.get("status") != "pass"
                    or not all(isinstance(effect.get(key), str) and effect[key].strip()
                               for key in ("artifact_id", "environment"))):
                raise ValueError("child integration or effect identity is unresolved")
    if (accepted["premerge"]["subject_sha"] != child.get("review_subject_sha")
            or accepted["complete"]["subject_sha"] != child.get("merged_sha")):
        raise ValueError("child acceptance subject changed")
    for phase, required, subject in (
        ("plan", child["plan_checkpoint"], child["review_subject_sha"]),
        ("complete", child["hitl"] or child["done_checkpoint"], child["merged_sha"]),
    ):
        if required:
            saved = child.get("checkpoint_decisions", {}).get(phase, {})
            gate.decision(workspace, saved.get("path"), saved.get("sha256"),
                          scope={"story": child["id"]}, phase=phase, sha=subject,
                          scope_digest=scope_digest(child))


def accept_epic(workspace, config, record, args):
    gate = gate_module()
    try:
        scoped, children, epics = epic_review_scope(workspace, config, record)
        if any(child["status"] not in TERMINAL for child in children):
            raise ValueError("epic still has open descendants; repeat the closure check")
        if any(epics[provider]["status"] != "done" for provider in record["needs"]):
            raise ValueError("epic prerequisite acceptance is unresolved")
        legacy = []
        for child in children:
            if child["status"] == "done" and child.get("accepted_gates", {}).get("complete"):
                validate_child_acceptance(workspace, child, args._strict_config_data)
            elif child["status"] == "done":
                if child.get("evidence_contract") == 1:
                    raise ValueError("new protected child cannot be accepted as legacy evidence")
                legacy.append(child["id"])
        content = gate.bound_read(workspace, args.decision)
        decision_digest = gate.digest(content)
        approval = gate.decision(workspace, args.decision, decision_digest,
                                 scope={"epic": record["id"]}, phase="epic", scope_digest=scoped)
        if (approval.get("legacy_children", []) != legacy
                or any(type(value) is not int for value in approval.get("legacy_children", []))):
            raise ValueError("legacy descendants need explicit independent reconciliation")
        evidence = approval.get("evidence")
        if args.evidence and (not isinstance(evidence, dict) or evidence.get("artifact") != args.evidence):
            raise ValueError("supplied epic evidence differs from the owner's reviewed bundle")
        reconciliation = gate.review_bundle(workspace, evidence, scoped, legacy)
        if reconciliation["reviewer"] in {child.get("owner") for child in children}:
            raise ValueError("epic reconciliation reviewer also owns child implementation")
        if record.get("acceptance"):
            record.setdefault("acceptance_history", []).append(record["acceptance"])
        record["acceptance"] = {"by": approval["approved_by"], "at": now(), "decision": args.decision,
                                "decision_sha256": decision_digest, "scope_sha256": scoped,
                                "evidence": evidence, "legacy_children": legacy,
                                "provenance_only": True}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError) as exc:
        raise BoardError(f"epic acceptance refused: {exc}") from exc


# -- configuration ------------------------------------------------------------


def board_config(workspace: Path, *, parsed_data=_UNSET):
    """Read the board keys from config.yaml; fail closed on malformed config."""
    config = {"dir": DEFAULT_BOARD_DIR, "regenerate": "on-write"}
    data = parsed_data
    if data is _UNSET:
        # Preserve trace's captured-only SnapshotPath reader contract.
        path = workspace / CONFIG_FILE
        if not path.is_file():
            return config
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise BoardError(
                "config: .software-factory/config.yaml is not valid JSON "
                "(the v1 JSON-compatible YAML subset); refusing to guess board paths"
            ) from exc
    elif data is None:
        return config
    if not isinstance(data, dict):
        raise BoardError("config: configuration must be an object at the top level")
    section = data.get("board")
    if section is None:
        return config
    if not isinstance(section, dict):
        raise BoardError("config: the board section must be an object")
    directory = section.get("dir", config["dir"])
    if not isinstance(directory, str) or not directory or Path(directory).is_absolute():
        raise BoardError("config: board.dir must be a workspace-relative path")
    regenerate = section.get("regenerate", config["regenerate"])
    if regenerate not in ("on-write", "manual"):
        raise BoardError("config: board.regenerate must be 'on-write' or 'manual'")
    return {"dir": directory, "regenerate": regenerate}


def board_dir(workspace: Path, config):
    directory = state_module().within(workspace, workspace / config["dir"])
    if directory.name == "context" or directory.parent == workspace:
        raise BoardError("config: board.dir must be a dedicated board directory")
    return directory


@contextmanager
def board_locked(workspace: Path):
    """The generator's lock, beside state.lock, with identical bounded wait."""
    state = state_module()
    directory = state.state_dir(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / BOARD_LOCK).open("a") as stream:
        deadline = time.monotonic() + state.LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BoardError(
                        "board busy; reconcile the active writer before regenerating"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


# -- record IO and validation ---------------------------------------------------


def read_record(path: Path):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_story(record):
    """None when valid, else the reason; unknown extra keys are ignored."""
    if record.get("version") != 1:
        return "version must be 1"
    if "evidence_contract" in record and (type(record["evidence_contract"]) is not int or record["evidence_contract"] != 1):
        return "unknown evidence contract"
    if not _is_int(record.get("id")):
        return "id must be a positive integer"
    if not _is_int(record.get("epic")):
        return "epic must be a positive integer id"
    if record.get("type") not in ("story", "bug", "spike"):
        return "type must be story, bug or spike"
    if not isinstance(record.get("title"), str) or not record["title"].strip():
        return "title must be a nonempty string"
    status = record.get("status")
    if status not in STATUSES:
        return f"unknown status {status!r}"
    if record.get("owner") is not None and not isinstance(record.get("owner"), str):
        return "owner must be a string or null"
    after = record.get("after")
    if not isinstance(after, list):
        return "after must be an array of story ids or {'epic': id} gates"
    for item in after:
        if _is_int(item):
            continue
        if isinstance(item, dict) and set(item) == {"epic"} and _is_int(item["epic"]):
            continue
        return "after entries must be story ids or {'epic': id} gates"
    if not _is_str_list(record.get("covers")):
        return "covers must be an array of requirement id strings"
    if not isinstance(record.get("risk"), str):
        return "risk must be a string"
    for key in ("hitl", "plan_checkpoint", "done_checkpoint"):
        if not isinstance(record.get(key), bool):
            return f"{key} must be a boolean"
    for key in ("sprint", "baseline_sha", "branch", "pr", "merged_sha", "source_key"):
        if key in record and record[key] is not None and not isinstance(record[key], str):
            return f"{key} must be a string"
    if "review_subject_sha" in record and (
        not isinstance(record["review_subject_sha"], str)
        or not gate_module().SHA1.fullmatch(record["review_subject_sha"])
    ):
        return "review_subject_sha must be a full Git SHA"
    for key in ("accepted_gates", "checkpoint_decisions"):
        if key in record and not isinstance(record[key], dict):
            return f"{key} must be an object"
    for key in ("gate_history", "checkpoint_history"):
        if key in record and not isinstance(record[key], list):
            return f"{key} must be an array"
    if "scope" in record and not _is_str_list(record.get("scope")):
        return "scope must be an array of repo-relative paths"
    blocked = record.get("blocked")
    if blocked is not None:
        reason = validate_blocked(blocked)
        if reason:
            return f"blocked: {reason}"
    receipts = record.get("receipts")
    if not isinstance(receipts, dict):
        return "receipts must be an object"
    for name, receipt in receipts.items():
        if not isinstance(name, str) or not isinstance(receipt, dict):
            return "receipts must map names to objects"
        if not isinstance(receipt.get("subject_sha"), str) or not receipt["subject_sha"]:
            return f"receipt {name!r} needs a subject_sha bound to what it proves"
    history = record.get("history")
    if not isinstance(history, list):
        return "history must be an array"
    for row in history:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) and row[key] for key in ("at", "by", "to")
        ):
            return "history rows need at, by, from and to"
    return None


def validate_blocked(blocked):
    if not isinstance(blocked, dict):
        return "must be an object or null"
    if set(blocked) - {"type", "reason", "since", "owner", "next_action"}:
        return "unknown keys (the blocked object is closed)"
    if blocked.get("type") not in BLOCKED_TYPES:
        return (
            f"type must be one of {', '.join(BLOCKED_TYPES)}; dependency waiting "
            "is derived from the after graph, never stored"
        )
    for key in ("reason", "since", "owner", "next_action"):
        if not isinstance(blocked.get(key), str) or not blocked[key].strip():
            return f"{key} must be a nonempty string"
    return None


def validate_epic(record):
    if record.get("version") != 1:
        return "version must be 1"
    if not _is_int(record.get("id")):
        return "id must be a positive integer"
    if not isinstance(record.get("title"), str) or not record["title"].strip():
        return "title must be a nonempty string"
    if not isinstance(record.get("outcome"), str):
        return "outcome must be a string"
    if not _is_str_list(record.get("done_when")):
        return "done_when must be an array of strings"
    if not _is_str_list(record.get("covers")):
        return "covers must be an array of requirement id strings"
    order = record.get("order")
    if not isinstance(order, list) or not all(_is_int(item) for item in order):
        return "order must be an array of story ids"
    needs = record.get("needs")
    if not isinstance(needs, list) or not all(_is_int(item) for item in needs):
        return "needs must be an array of epic ids"
    status = record.get("status")
    if status not in EPIC_STATUSES:
        return f"unknown epic status {status!r}"
    if not isinstance(record.get("history", []), list):
        return "history must be an array"
    return None


def load_board(directory: Path):
    """Load and validate every record; degenerate entries become problems."""
    problems = []
    streams_doc = read_record(directory / "streams.json")
    if (
        not streams_doc
        or streams_doc.get("version") != 1
        or not isinstance(streams_doc.get("streams"), list)
    ):
        raise BoardError("board: streams.json missing or invalid; reconcile the board")
    streams = []
    for entry in streams_doc["streams"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not entry["id"].startswith("W-")
            or not isinstance(entry.get("title"), str)
            or entry.get("status") not in ("active", "paused", "done")
            or not isinstance(entry.get("epics"), list)
            or not all(_is_int(item) for item in entry["epics"])
        ):
            raise BoardError(
                f"board: invalid stream entry {entry.get('id')!r} in streams.json; "
                "reconcile the board"
            )
        streams.append(entry)
    meta = read_record(directory / "meta.json")
    if (
        not meta
        or meta.get("version") != 1
        or not _is_int(meta.get("next_story_id"))
        or not _is_int(meta.get("next_epic_id"))
    ):
        raise BoardError("board: meta.json missing or invalid; reconcile the board")
    epics = {}
    for path in sorted((directory / "epics").glob("*.json")) if (directory / "epics").is_dir() else []:
        record = read_record(path)
        reason = None if record is None else validate_epic(record)
        if record is None or reason:
            problems.append(
                {"file": f"epics/{path.name}", "reason": reason or "unreadable or not an object"}
            )
            continue
        if record["id"] in epics:
            problems.append({"file": f"epics/{path.name}", "reason": f"duplicate epic id {record['id']}"})
            continue
        epics[record["id"]] = record
    stories = {}
    stories_dir = directory / "stories"
    if stories_dir.is_dir():
        for path in sorted(stories_dir.glob("*.json")):
            record = read_record(path)
            reason = None if record is None else validate_story(record)
            if record is None or reason:
                problems.append(
                    {"file": f"stories/{path.name}", "story": _maybe_int(path.stem),
                     "reason": reason or "unreadable or not an object"}
                )
                continue
            if record["id"] in stories:
                problems.append(
                    {"file": f"stories/{path.name}", "story": record["id"],
                     "reason": f"duplicate story id {record['id']}"}
                )
                continue
            stories[record["id"]] = record
    return streams, meta, epics, stories, problems


def _maybe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def write_record(path: Path, record):
    state_module().atomic_json(path, record)


# -- claims: read-only mirror of the exclusivity system of record ----------------


def live_claims(workspace: Path):
    """Read live claims from the run state; never writes, never expires them."""
    state = state_module()
    try:
        pointer = state.pointer_path(workspace)
        try:
            pointer.lstat()
        except FileNotFoundError:
            return {}  # No active program is valid; a broken existing pointer is not.
        _, data = state.load(workspace)
    except (state.StateError, OSError) as exc:
        raise BoardError(
            "the claims state exists but is unreadable; reconcile it with "
            "state.py repair before worker board updates"
        ) from exc
    return data["claims"]


def claims_or_empty(workspace: Path):
    """Claims for projection builds: tolerate a missing run, report a broken one."""
    try:
        return live_claims(workspace), None
    except BoardError as exc:
        return {}, str(exc)


# -- derive: planning source -> records ------------------------------------------


def new_story(story_id, epic_id, epic_key, source):
    return {
        "version": 1,
        "evidence_contract": 1,
        "id": story_id,
        "epic": epic_id,
        "type": source.get("type", "story"),
        "title": source["title"],
        "status": "backlog",
        "owner": None,
        "after": [],
        "covers": list(source.get("covers", [])),
        "risk": source.get("risk", ""),
        "hitl": bool(source.get("hitl", False)),
        "plan_checkpoint": bool(source.get("plan_checkpoint", False)),
        "done_checkpoint": bool(source.get("done_checkpoint", False)),
        "blocked": None,
        "receipts": {},
        "baseline_sha": None,
        "branch": None,
        "pr": None,
        "merged_sha": None,
        "history": [],
        "findings": [],
        "source_key": f"{epic_key}/{source['key']}",
    }


def new_epic(epic_id, source):
    return {
        "version": 1,
        "id": epic_id,
        "title": source["title"],
        "outcome": source.get("outcome", ""),
        "done_when": list(source.get("done_when", [])),
        "covers": list(source.get("covers", [])),
        "order": [],
        "needs": [],
        "status": "planned",
        "acceptance": None,
        "parked": None,
        "park_proposal": None,
        "history": [],
        "source_key": source["key"],
    }


def refresh_story(record, source, epic_id, after):
    """Update structure fields only; status, receipts and history are live data."""
    record["epic"] = epic_id
    record["type"] = source.get("type", record.get("type", "story"))
    record["title"] = source["title"]
    record["after"] = after
    record["covers"] = list(source.get("covers", []))
    record["risk"] = source.get("risk", record.get("risk", ""))
    for key in ("hitl", "plan_checkpoint", "done_checkpoint"):
        if key in source:
            record[key] = bool(source[key])
    for key in ("sprint", "scope"):
        if key in source:
            record[key] = source[key]
        else:
            record.pop(key, None)
    return record


def check_id_counters(directory, meta, epics, stories):
    """Fail closed before minting: each meta.json counter must exceed every
    existing record id and collide with no record file on disk. A stale
    counter means the board drifted from its records; repairing it is an
    explicit operator edit of meta.json, never an implicit overwrite of a
    live record.
    """
    for key, records, subdir, noun in (
        ("next_story_id", stories, "stories", "story"),
        ("next_epic_id", epics, "epics", "epic"),
    ):
        counter = meta[key]
        highest = max(records, default=0)
        if counter <= highest:
            raise BoardError(
                f"meta.json {key} is {counter} but {noun} id {highest} already "
                "exists; ids are assigned once and never reused — set "
                f"{key} above {highest} in meta.json, then re-run derive"
            )
        file_ids = []
        for path in (directory / subdir).glob("*.json"):
            stem = _maybe_int(path.stem)
            if isinstance(stem, int) and stem >= counter:
                file_ids.append(stem)
        if file_ids:
            raise BoardError(
                f"meta.json {key} {counter} would mint an id that collides with "
                f"existing record file {subdir}/{min(file_ids)}.json; records join "
                "by id, never by filename — reconcile the board, then re-run derive"
            )


def derive(workspace: Path, source_path: Path):
    """Create or refresh board records from the planning source document.

    Joins planning entries to records by source_key; ids come from the
    never-reused counters in meta.json, verified against the existing
    records before anything is written. Live fields (status, receipts,
    history, blocked) are never touched.
    """
    try:
        source = json.loads(Path(source_path).read_text())
    except (OSError, ValueError) as exc:
        raise BoardError(f"planning source unreadable or not JSON: {exc.__class__.__name__}") from exc
    if not isinstance(source, dict) or not isinstance(source.get("epics"), list):
        raise BoardError("planning source must be an object with an epics array")
    config = board_config(workspace)
    directory = board_dir(workspace, config)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "epics").mkdir(exist_ok=True)
    (directory / "stories").mkdir(exist_ok=True)
    if not (directory / "streams.json").exists():
        write_record(directory / "streams.json", {"version": 1, "streams": []})
    if not (directory / "meta.json").exists():
        write_record(directory / "meta.json", {"version": 1, "next_story_id": 1, "next_epic_id": 1})
    with board_locked(workspace):
        streams, meta, epics, stories, problems = load_board(directory)
        if problems:
            named = ", ".join(item["file"] for item in problems)
            raise BoardError(f"degenerate records block a structural derive: {named}")
        check_id_counters(directory, meta, epics, stories)
        frozen_epics = {key: json.dumps(record, sort_keys=True) for key, record in epics.items()
                        if record["status"] in TERMINAL}
        frozen_stories = {key: json.dumps(record, sort_keys=True) for key, record in stories.items()
                          if record["status"] in TERMINAL or record["epic"] in frozen_epics}
        frozen_membership = {key: [stream["id"] for stream in streams if key in stream["epics"]]
                             for key in frozen_epics}
        frozen_children = {key: {story["id"] for story in stories.values() if story["epic"] == key}
                           for key in frozen_epics}
        epics_by_key = {e.get("source_key"): e for e in epics.values() if e.get("source_key")}
        stories_by_key = {s.get("source_key"): s for s in stories.values() if s.get("source_key")}
        streams_by_id = {s["id"]: s for s in streams}

        for stream in source.get("streams", []):
            if not isinstance(stream, dict) or not isinstance(stream.get("id"), str):
                raise BoardError("each planning stream needs an id")
            existing = streams_by_id.get(stream["id"])
            if existing is None:
                existing = {
                    "id": stream["id"],
                    "title": stream.get("title", stream["id"]),
                    "status": stream.get("status", "active"),
                    "epics": [],
                }
                streams.append(existing)
                streams_by_id[stream["id"]] = existing
            else:
                existing["title"] = stream.get("title", existing["title"])
                existing["status"] = stream.get("status", existing["status"])

        # Pass 1: upsert epics so ids exist for need/after resolution.
        declared_streams = []
        for epic_source in source["epics"]:
            if not isinstance(epic_source, dict) or not epic_source.get("key"):
                raise BoardError("each planning epic needs a key")
            stream_id = epic_source.get("stream")
            if stream_id not in streams_by_id:
                raise BoardError(f"epic {epic_source['key']!r} names unknown stream {stream_id!r}")
            declared_streams.append((epic_source["key"], stream_id))
            if epic_source["key"] not in epics_by_key:
                epic = new_epic(meta["next_epic_id"], epic_source)
                meta["next_epic_id"] += 1
                epics[epic["id"]] = epic
                epics_by_key[epic_source["key"]] = epic

        # Pass 2: upsert every story so ids exist for forward references.
        for epic_source in source["epics"]:
            epic = epics_by_key[epic_source["key"]]
            epic["title"] = epic_source.get("title", epic["title"])
            if "outcome" in epic_source:
                epic["outcome"] = epic_source["outcome"]
            for key in ("done_when", "covers"):
                if key in epic_source:
                    epic[key] = list(epic_source[key])
            needs = []
            for need in epic_source.get("needs", []):
                if need not in epics_by_key:
                    raise BoardError(
                        f"epic {epic_source['key']!r} needs unknown epic {need!r}"
                    )
                target = epics_by_key[need]["id"]
                if target == epic["id"]:
                    raise BoardError(f"epic {epic_source['key']!r} cannot need itself")
                needs.append(target)
            epic["needs"] = needs
            for story_source in epic_source.get("stories", []):
                if not isinstance(story_source, dict) or not story_source.get("key"):
                    raise BoardError(f"each story in epic {epic_source['key']!r} needs a key")
                if not story_source.get("title"):
                    raise BoardError(f"story {story_source['key']!r} needs a title")
                source_key = f"{epic_source['key']}/{story_source['key']}"
                if source_key not in stories_by_key:
                    story = new_story(meta["next_story_id"], epic["id"],
                                      epic_source["key"], story_source)
                    meta["next_story_id"] += 1
                    stories[story["id"]] = story
                    stories_by_key[source_key] = story

        # Pass 3: resolve afters and refresh structure fields and build order.
        for epic_source in source["epics"]:
            epic = epics_by_key[epic_source["key"]]
            order = []
            for story_source in epic_source.get("stories", []):
                source_key = f"{epic_source['key']}/{story_source['key']}"
                after = resolve_after(story_source.get("after", []), epic_source["key"],
                                      epics_by_key, stories_by_key)
                story = refresh_story(stories_by_key[source_key], story_source,
                                      epic["id"], after)
                order.append(story["id"])
            prior = [item for item in epic.get("order", []) if item not in order]
            epic["order"] = order + prior

        # Rebuild stream membership and order: source order first, then any
        # previously known epics the source does not mention (never deleted).
        declared_by_stream = {}
        for key, stream_id in declared_streams:
            declared_by_stream.setdefault(stream_id, []).append(epics_by_key[key]["id"])
        for stream in streams:
            declared = declared_by_stream.get(stream["id"], [])
            stream["epics"] = declared + [e for e in stream["epics"] if e not in declared]

        # Derivation is a structural proposal, never authority to rewrite accepted
        # scope or cancelled history. Refuse the entire proposal before publication.
        for noun, frozen, current in (("epic", frozen_epics, epics),
                                      ("story", frozen_stories, stories)):
            for key, original in frozen.items():
                if json.dumps(current[key], sort_keys=True) != original:
                    raise BoardError(f"{noun} {key} is frozen terminal history; "
                                     "route changed scope to new work and a decision")
        for key, children in frozen_children.items():
            if {story["id"] for story in stories.values() if story["epic"] == key} != children:
                raise BoardError(f"epic {key} has frozen terminal child membership; "
                                 "route changed scope to new work and a decision")
        for key, membership in frozen_membership.items():
            if [stream["id"] for stream in streams if key in stream["epics"]] != membership:
                raise BoardError(f"epic {key} has frozen terminal stream membership; "
                                 "route changed scope to new work and a decision")

        write_record(directory / "streams.json", {"version": 1, "streams": streams})
        write_record(directory / "meta.json", meta)
        for epic in epics.values():
            if epic["id"] not in frozen_epics:
                write_record(directory / "epics" / f"{epic['id']}.json", epic)
        for story in stories.values():
            if story["id"] not in frozen_stories:
                write_record(directory / "stories" / f"{story['id']}.json", story)
    return len(epics), len(stories)


def resolve_after(after, epic_key, epics_by_key, stories_by_key):
    """Resolve planning-source after entries to story ids / epic gates."""
    resolved = []
    for item in after:
        if isinstance(item, dict) and set(item) == {"epic"}:
            target = epics_by_key.get(item["epic"])
            if target is None:
                raise BoardError(f"unknown epic gate {item['epic']!r} in the planning source")
            resolved.append({"epic": target["id"]})
            continue
        if not isinstance(item, str):
            raise BoardError(f"invalid after entry {item!r} in the planning source")
        key = item if "/" in item else f"{epic_key}/{item}"
        target = stories_by_key.get(key)
        if target is None:
            raise BoardError(f"unknown story reference {item!r} in the planning source")
        resolved.append(target["id"])
    return resolved


# -- transitions: who-transitions-what, enforced in code ---------------------------


def story_path(workspace: Path, config, story_id):
    directory = board_dir(workspace, config)
    path = directory / "stories" / f"{story_id}.json"
    record = read_record(path)
    reason = None if record is None else validate_story(record)
    if record is None or reason:
        raise BoardError(
            f"story {story_id} has no valid record ({reason or 'missing'}); "
            "reconcile the board before updating it"
        )
    return path, record


def require_frozen_check(record):
    if record["status"] in TERMINAL:
        raise BoardError(
            f"story {record['id']} is {record['status']}; terminal records are frozen "
            "history — a correction is a decision record or a new story, never a rewrite"
        )


def history_row(record, by, to):
    record.setdefault("history", []).append(
        {"at": now(), "by": by, "from": record["status"], "to": to}
    )


def add_receipts(record, receipt_args):
    for item in receipt_args:
        name, sep, file_name = item.partition("=")
        if not sep or not name.strip():
            raise BoardError("receipts are passed as name=<json-file>")
        try:
            receipt = json.loads(Path(file_name).read_text())
        except (OSError, ValueError) as exc:
            raise BoardError(f"receipt {name!r} is not a readable JSON file") from exc
        if not isinstance(receipt, dict) or not isinstance(receipt.get("subject_sha"), str) \
                or not receipt["subject_sha"]:
            raise BoardError(
                f"receipt {name!r} needs a subject_sha bound to the evidence subject"
            )
        record.setdefault("receipts", {})[name.strip()] = receipt


def apply_blocked(record, args):
    if args.unblock:
        record["blocked"] = None
        return
    if not args.block:
        return
    missing = [flag for flag, value in (
        ("--reason", args.reason), ("--block-owner", args.block_owner),
        ("--next-action", args.next_action),
    ) if not value]
    if missing:
        raise BoardError(f"blocking needs {', '.join(missing)}")
    blocked = {
        "type": args.block,
        "reason": args.reason,
        "since": now(),
        "owner": args.block_owner,
        "next_action": args.next_action,
    }
    reason = validate_blocked(blocked)
    if reason:
        raise BoardError(f"blocked: {reason}")
    record["blocked"] = blocked


def worker_update(record, args, claims):
    story_id = record["id"]
    claim = claims.get(str(story_id))
    if claim is None:
        raise BoardError(
            f"no live claim for story {story_id}; claim the story's paths with "
            "state.py claim first — the claim is the checkout"
        )
    if claim.get("owner") != args.owner:
        raise BoardError(
            f"owner mismatch for story {story_id}; the live claim belongs to its "
            "owner — reconcile before writing another worker's record"
        )
    if args.status is not None:
        current = record["status"]
        if args.status == "in-progress":
            if current not in ("ready-for-dev", "in-review", "built"):
                raise BoardError(
                    f"story {story_id} is {current}; the orchestrator moves a story to "
                    "ready-for-dev before a worker can start it"
                )
            if current in ("in-review", "built"):
                if record.get("accepted_gates"):
                    record.setdefault("gate_history", []).append(record.pop("accepted_gates"))
                record.pop("review_subject_sha", None)
        elif args.status == "in-review":
            if current != "in-progress":
                raise BoardError(f"story {story_id} is {current}; only in-progress work enters review")
            if not record.get("receipts") and not args.receipt:
                raise BoardError(
                    "in-review needs at least one receipt bound to the story HEAD "
                    "(--receipt name=<json-file> with a subject_sha)"
                )
        elif args.status in ("built", "done"):
            raise BoardError(
                f"the orchestrator owns the {args.status} gate transition; workers "
                "self-serve in-progress, in-review, blocked and receipts"
            )
        else:
            raise BoardError(
                f"workers cannot move a story to {args.status}; workers self-serve "
                "in-progress, in-review, blocked and receipts"
            )
    apply_blocked(record, args)
    add_receipts(record, args.receipt or [])
    if args.status == "in-review":
        subjects = {receipt.get("subject_sha") for receipt in record["receipts"].values()}
        subject = args.sha or (next(iter(subjects)) if len(subjects) == 1 else None)
        if not isinstance(subject, str) or not gate_module().SHA1.fullmatch(subject) or subject not in subjects:
            raise BoardError("in-review needs the full current --sha matching a submitted receipt")
        record["review_subject_sha"] = subject
        record["evidence_contract"] = 1
    if args.finding:
        record.setdefault("findings", []).append({"at": now(), "by": args.owner, "text": args.finding})
    if args.status is not None:
        history_row(record, args.owner, args.status)
        record["status"] = args.status
        if args.status == "in-progress":
            record["owner"] = args.owner


def orchestrator_update(workspace, config, record, args):
    story_id = record["id"]
    if args.status is not None:
        current = record["status"]
        if args.status == "ready-for-dev":
            if current != "backlog":
                raise BoardError(f"story {story_id} is {current}; ready-for-dev comes from backlog")
            if record["plan_checkpoint"]:
                required_checkpoint(workspace, record, args, "plan", args.sha)
        elif args.status == "built":
            if current != "in-review":
                raise BoardError(f"story {story_id} is {current}; built comes from in-review")
            unmet = unmet_dependencies(workspace, config, record, for_merge=True)
            if unmet:
                raise BoardError(
                    f"story {story_id} cannot reach built before its providers merge: "
                    + "; ".join(unmet)
                )
            protected_gate(workspace, record, args, "premerge")
        elif args.status == "done":
            if current != "built":
                raise BoardError(
                    f"story {story_id} is {current}; only the merge step moves built work to done"
                )
            protected_gate(workspace, record, args, "complete")
            record["merged_sha"] = args.sha
        elif args.status == "cancelled":
            if not args.reason:
                raise BoardError("a cancellation proposal needs --reason")
            record["cancel_proposal"] = {"by": "orchestrator", "reason": args.reason, "at": now()}
            apply_blocked(record, args)
            add_receipts(record, args.receipt or [])
            return  # a proposal does not move the status
        else:
            raise BoardError(
                f"the orchestrator cannot move a story to {args.status}; it owns "
                "ready-for-dev, built, done and cancellation proposals"
            )
    apply_blocked(record, args)
    add_receipts(record, args.receipt or [])
    if args.finding:
        record.setdefault("findings", []).append({"at": now(), "by": "orchestrator", "text": args.finding})
    if args.status is not None:
        history_row(record, "orchestrator", args.status)
        record["status"] = args.status


def human_update(record, args):
    story_id = record["id"]
    if args.status != "cancelled":
        raise BoardError(
            "the human story-level action is confirming a proposed cancellation "
            "(--status cancelled --decision <ref>); epic acceptance uses the epic command"
        )
    if record["status"] == "cancelled":
        raise BoardError(f"story {story_id} is already cancelled")
    proposal = record.get("cancel_proposal")
    if not isinstance(proposal, dict):
        raise BoardError(
            f"story {story_id} has no cancellation proposal; the orchestrator "
            "proposes, the human confirms"
        )
    if not args.decision:
        raise BoardError("confirming a cancellation needs --decision <decision-record-ref>")
    history_row(record, "human", "cancelled")
    record["status"] = "cancelled"
    record["cancellation"] = {
        "by": "human", "decision": args.decision, "at": now(),
        "reason": proposal.get("reason", ""),
    }
    record["cancel_proposal"] = None


def unmet_dependencies(workspace, config, record, for_merge=False):
    """Human-readable unmet prerequisites; merge-level needs providers done."""
    directory = board_dir(workspace, config)
    _, _, epics, stories, _ = load_board(directory)
    unmet = []
    for item in record.get("after", []):
        if isinstance(item, dict):
            epic = epics.get(item["epic"])
            if epic is None or epic["status"] != "done":
                state = epic["status"] if epic else "unknown"
                unmet.append(f"epic {item['epic']} gate ({state})")
            continue
        provider = stories.get(item)
        if provider is None:
            unmet.append(f"story {item} (unknown)")
            continue
        if for_merge:
            if provider["status"] != "done":
                unmet.append(f"story {item} ({provider['status']}, not done)")
        elif provider["status"] not in MET_STATUSES:
            unmet.append(f"story {item} ({provider['status']})")
    return unmet


def update_story(workspace: Path, args):
    config = transition_config(workspace, args)
    try:
        story_id = int(args.story)
    except (TypeError, ValueError) as exc:
        raise BoardError("story id must be a positive integer") from exc
    if story_id < 1:
        raise BoardError("story id must be a positive integer")
    with board_locked(workspace):
        path, record = story_path(workspace, config, story_id)
        if record["status"] in TERMINAL and not (
            args.actor == "human" and args.status == "cancelled" and record["status"] == "cancelled"
        ):
            require_frozen_check(record)
        if args.actor == "worker":
            if not args.owner:
                raise BoardError("worker updates need --owner matching the live claim owner")
            worker_update(record, args, live_claims(workspace))
        elif args.actor == "orchestrator":
            orchestrator_update(workspace, config, record, args)
        elif args.actor == "human":
            human_update(record, args)
        else:
            raise BoardError("actor must be worker, orchestrator or human")
        invalid = validate_story(record)
        if invalid:
            raise BoardError(f"the update would leave story {story_id} invalid: {invalid}")
        write_record(path, record)
    return record


# -- epic transitions -------------------------------------------------------------


def epic_update(workspace: Path, args):
    config = transition_config(workspace, args)
    directory = board_dir(workspace, config)
    epic_id = int(args.epic)
    with board_locked(workspace):
        path, record = None, None
        candidate = directory / "epics" / f"{epic_id}.json"
        record = read_record(candidate)
        reason = None if record is None else validate_epic(record)
        if record is None or reason:
            raise BoardError(f"epic {epic_id} has no valid record ({reason or 'missing'})")
        path = candidate
        current = record["status"]
        if current in ("done", "cancelled"):
            raise BoardError(
                f"epic {epic_id} is {current}; terminal epic records are frozen history"
            )
        if args.actor == "orchestrator":
            if args.status == "in-progress":
                if current not in ("planned", "parked"):
                    raise BoardError(f"epic {epic_id} is {current}")
                history_row(record, "orchestrator", "in-progress")
                record["status"] = "in-progress"
                if current == "parked":
                    record["parked"] = None
            elif args.status == "awaiting-acceptance":
                _, _, _epics, stories, _ = load_board(directory)
                open_stories = [
                    s["id"] for s in stories.values()
                    if s["epic"] == epic_id and s["status"] not in TERMINAL
                ]
                if open_stories:
                    raise BoardError(
                        f"epic {epic_id} still has open stories {open_stories}; closing "
                        "children never closes the parent — finish or cancel them first"
                    )
                history_row(record, "orchestrator", "awaiting-acceptance")
                record["status"] = "awaiting-acceptance"
            elif args.status == "parked":
                if not args.resume:
                    raise BoardError("a park proposal needs --resume (branch/tip + conditions)")
                record["park_proposal"] = {
                    "by": "orchestrator", "resume": args.resume, "at": now(),
                }
            else:
                raise BoardError(
                    "the orchestrator moves epics to in-progress or awaiting-acceptance "
                    "and proposes parks; humans accept, park and cancel"
                )
        elif args.actor == "human":
            if args.status == "done":
                if current != "awaiting-acceptance":
                    raise BoardError(
                        f"epic {epic_id} is {current}; the orchestrator moves it to "
                        "awaiting-acceptance after the closure check, then a human accepts"
                    )
                accept_epic(workspace, config, record, args)
                history_row(record, "human", "done")
                record["status"] = "done"
            elif args.status == "parked":
                proposal = record.get("park_proposal")
                if not isinstance(proposal, dict):
                    raise BoardError(
                        f"epic {epic_id} has no park proposal; the orchestrator proposes "
                        "with a resume pointer, the human confirms"
                    )
                history_row(record, "human", "parked")
                record["status"] = "parked"
                record["parked"] = {"resume": proposal["resume"], "at": now()}
                record["park_proposal"] = None
            elif args.status == "cancelled":
                if not args.decision:
                    raise BoardError("cancelling an epic needs --decision <decision-record-ref>")
                history_row(record, "human", "cancelled")
                record["status"] = "cancelled"
                record["cancellation"] = {"by": "human", "decision": args.decision, "at": now()}
                _, _, _, stories, _ = load_board(directory)
                for story in stories.values():
                    if story["epic"] == epic_id and story["status"] not in TERMINAL:
                        history_row(story, "human", "cancelled")
                        story["status"] = "cancelled"
                        story["cancellation"] = {
                            "by": "human", "decision": args.decision, "at": now(),
                            "reason": f"epic {epic_id} cancelled",
                        }
                        story["cancel_proposal"] = None
                        write_record(directory / "stories" / f"{story['id']}.json", story)
            else:
                raise BoardError("humans accept (done), confirm parked, or cancel epics")
        else:
            raise BoardError("epic transitions are written by the orchestrator or a human")
        write_record(path, record)
    return record


# -- the projection ---------------------------------------------------------------


def find_cycle(stories, epics):
    """One dependency cycle as an id path, or None; gates expand to members."""
    members = {}
    for story in stories.values():
        members.setdefault(story["epic"], []).append(story["id"])

    def deps(story):
        for item in story.get("after", []):
            if isinstance(item, dict):
                yield from members.get(item["epic"], [])
            else:
                yield item

    color = {}
    path = []

    def visit(node):
        color[node] = 1
        path.append(node)
        for nxt in deps(stories[node]):
            if nxt not in stories:
                continue
            if color.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if color.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        color[node] = 2
        return None

    for story_id in sorted(stories):
        if color.get(story_id, 0) == 0:
            found = visit(story_id)
            if found:
                return found
    return None


def critical_paths(stories, stream_of):
    """Longest remaining chain per stream, following same-stream after links."""
    memo = {}

    def chain(story_id):
        if story_id in memo:
            return memo[story_id]
        story = stories[story_id]
        best = []
        for item in story.get("after", []):
            if isinstance(item, dict):
                continue  # epic gates bound readiness, not the chain length
            if item not in stories or stream_of.get(item) != stream_of.get(story_id):
                continue
            if stories[item]["status"] in TERMINAL:
                continue
            candidate = chain(item)
            if len(candidate) > len(best):
                best = candidate
        memo[story_id] = [*best, story_id]
        return memo[story_id]

    per_stream = {}
    for story_id, story in stories.items():
        if story["status"] in TERMINAL:
            continue
        stream = stream_of.get(story_id)
        if stream is None:
            continue
        candidate = chain(story_id)
        current = per_stream.get(stream, [])
        if len(candidate) > len(current):
            per_stream[stream] = candidate
    return per_stream


def compute_roadmap(workspace: Path, config, directory: Path):
    """Derive the full projection from the records plus a read-only claims mirror."""
    streams, _meta, epics, stories, problems = load_board(directory)

    # Membership: an epic joins its stream through the stream's epics array.
    stream_of_epic = {}
    for stream in streams:
        for epic_id in stream["epics"]:
            if epic_id in stream_of_epic:
                problems.append({"file": "streams.json", "reason": f"epic {epic_id} listed by two streams"})
            stream_of_epic[epic_id] = stream["id"]
    for epic_id in epics:
        if epic_id not in stream_of_epic:
            problems.append({"file": f"epics/{epic_id}.json", "epic": epic_id,
                             "reason": "epic is not listed in any stream's epics array"})
    stream_of = {}
    for story_id, story in stories.items():
        if story["epic"] not in epics:
            problems.append({"file": f"stories/{story_id}.json", "story": story_id,
                             "reason": f"story joins unknown epic {story['epic']}"})
            continue
        if story["epic"] not in stream_of_epic:
            continue
        stream_of[story_id] = stream_of_epic[story["epic"]]

    cycle = find_cycle(stories, epics)
    if cycle:
        raise BoardError(
            "dependency cycle rejected at load: " + " -> ".join(str(node) for node in cycle)
        )

    claims, claims_problem = claims_or_empty(workspace)
    if claims_problem:
        problems.append({"file": "active.json", "reason": claims_problem})

    # Structural reference checks (dangling refs are problems, never crashes).
    for story_id, story in sorted(stories.items()):
        for item in story.get("after", []):
            if isinstance(item, dict):
                if item["epic"] not in epics:
                    problems.append({"story": story_id, "reason": f"after gate joins unknown epic {item['epic']}"})
            elif item not in stories:
                problems.append({"story": story_id, "reason": f"after joins unknown story {item}"})

    # Diagnostics.
    unpinned_gates = []
    undeclared_after = []
    order_conflicts = []
    for epic_id, epic in sorted(epics.items()):
        for need in epic.get("needs", []):
            pinned = False
            for story in stories.values():
                if story["epic"] != epic_id:
                    continue
                for item in story.get("after", []):
                    if (isinstance(item, dict) and item["epic"] == need) or (
                        not isinstance(item, dict) and item in stories
                        and stories[item]["epic"] == need
                    ):
                        pinned = True
            if not pinned:
                unpinned_gates.append(
                    {"epic": epic_id, "needs": need,
                     "detail": f"epic {epic_id} declares a need on epic {need} but no story pins it"}
                )
        order = epic.get("order", [])
        position = {story_id: index for index, story_id in enumerate(order)}
        for story_id, story in sorted(stories.items()):
            if story["epic"] != epic_id:
                continue
            for item in story.get("after", []):
                if isinstance(item, dict):
                    continue
                other = stories.get(item)
                if other is None:
                    continue
                if other["epic"] != epic_id and other["epic"] not in epic.get("needs", []):
                    undeclared_after.append(
                        {"story": story_id, "depends_on": item,
                         "detail": f"story {story_id} waits on story {item} of epic "
                                   f"{other['epic']}, which epic {epic_id} does not declare in needs"}
                    )
                if other["epic"] == epic_id and story_id in position and item in position \
                        and position[item] > position[story_id]:
                    order_conflicts.append(
                        {"epic": epic_id, "story": story_id, "prerequisite": item,
                         "detail": f"epic {epic_id} order places story {story_id} before "
                                   f"its prerequisite {item}"}
                    )
    for stream in streams:
        position = {epic_id: index for index, epic_id in enumerate(stream["epics"])}
        for epic_id in stream["epics"]:
            epic = epics.get(epic_id)
            if epic is None:
                problems.append({"file": "streams.json", "reason": f"stream {stream['id']} lists unknown epic {epic_id}"})
                continue
            for need in epic.get("needs", []):
                if need in position and position[need] > position[epic_id]:
                    order_conflicts.append(
                        {"stream": stream["id"], "epic": epic_id, "depends_on": need,
                         "detail": f"stream {stream['id']} orders epic {epic_id} before "
                                   f"epic {need}, which it depends on"}
                    )

    # Derived states, readiness, frontier.
    derived = {}
    frontier_ready = []
    waiting = []
    for story_id, story in sorted(stories.items()):
        if story_id not in stream_of:
            continue
        status = story["status"]
        missing = []
        met_parts = []
        for item in story.get("after", []):
            if isinstance(item, dict):
                epic = epics.get(item["epic"])
                if epic is None or epic["status"] != "done":
                    missing.append(
                        f"epic {item['epic']} gate ({epic['status'] if epic else 'unknown'})"
                    )
                else:
                    met_parts.append(f"epic {item['epic']} gate done")
            else:
                provider = stories.get(item)
                if provider is None:
                    missing.append(f"{item} (unknown)")
                elif provider["status"] in MET_STATUSES:
                    met_parts.append(f"{item} {provider['status']}")
                elif provider["status"] == "cancelled":
                    missing.append(f"{item} (cancelled; repoint the dependency)")
                else:
                    missing.append(f"{item} ({provider['status']})")
        deps_met = not missing
        claim = claims.get(str(story_id))
        if status in ("backlog", "ready-for-dev"):
            state = "ready" if deps_met and not story.get("blocked") and not claims_problem else "planned"
        else:
            state = {
                "in-progress": "in-progress", "in-review": "review",
                "built": "built", "done": "done", "cancelled": "cancelled",
            }[status]
        derived[story_id] = (state, deps_met, missing, met_parts)
        if status in ("backlog", "ready-for-dev"):
            if not deps_met:
                waiting.append({"id": story_id, "epic": story["epic"],
                                "stream": stream_of[story_id], "title": story["title"],
                                "missing": missing})
            elif not story.get("blocked") and claim is None and not claims_problem:
                why = "; ".join([*(f"after {part}" for part in met_parts)] or ["no prerequisites"])
                frontier_ready.append({"id": story_id, "epic": story["epic"],
                                       "stream": stream_of[story_id], "title": story["title"],
                                       "why": f"{why}; unclaimed", "claimed": False})

    # Blocked-by inversion and the blockers panel.
    blocks = {story_id: [] for story_id in stories}
    for story_id, story in stories.items():
        for item in story.get("after", []):
            if isinstance(item, dict):
                for member in stories.values():
                    if member["epic"] == item["epic"] and story_id != member["id"]:
                        blocks.setdefault(member["id"], []).append(story_id)
            elif item in blocks:
                blocks[item].append(story_id)

    def stalled_chain(story_id):
        seen = []
        queue = list(blocks.get(story_id, []))
        while queue:
            current = queue.pop(0)
            if current in seen or current not in stories:
                continue
            seen.append(current)
            if stories[current]["status"] in TERMINAL:
                continue
            queue.extend(blocks.get(current, []))
        return seen

    blockers = []
    for story_id, story in sorted(stories.items()):
        blocked = story.get("blocked")
        if blocked:
            blockers.append({
                "id": story_id, "epic": story["epic"], "stream": stream_of.get(story_id),
                "type": blocked["type"], "reason": blocked["reason"],
                "owner": blocked["owner"], "since": blocked["since"],
                "next_action": blocked["next_action"], "stalls": stalled_chain(story_id),
            })
    blockers.sort(key=lambda entry: (entry["since"], entry["id"]))

    # Claims/record inconsistencies, surfaced and never auto-repaired.
    inconsistencies = []
    for story_id, story in sorted(stories.items()):
        claim = claims.get(str(story_id))
        if story["status"] == "in-progress" and claim is None:
            inconsistencies.append({
                "kind": "in-progress-without-claim", "story": story_id,
                "detail": f"story {story_id} is in-progress but holds no live claim",
            })
        if claim is not None and story.get("scope"):
            outside = [
                path for path in claim.get("paths", [])
                if not any(
                    path == scope or path.startswith(scope.rstrip("/") + "/")
                    for scope in story["scope"]
                )
            ]
            if outside:
                inconsistencies.append({
                    "kind": "claim-outside-scope", "story": story_id, "paths": outside,
                    "detail": f"claim for story {story_id} covers paths outside its "
                              f"declared scope: {', '.join(sorted(outside))}",
                })
    for task, claim in sorted(claims.items()):
        if task.isdigit() and int(task) in stories:
            continue
        inconsistencies.append({
            "kind": "claim-without-record", "task": task,
            "owner": claim.get("owner", "unknown"),
            "detail": f"claim {task} ({claim.get('owner', 'unknown')}) matches no story record",
        })

    # The decision queue: everything waiting on a human.
    decision_queue = []
    for blocker in blockers:
        if blocker["type"] == "human-decision":
            decision_queue.append({
                "kind": "blocked", "story": blocker["id"], "question": blocker["reason"],
                "owner": blocker["owner"], "next_action": blocker["next_action"],
            })
    for story_id, story in sorted(stories.items()):
        proposal = story.get("cancel_proposal")
        if isinstance(proposal, dict):
            decision_queue.append({
                "kind": "cancel-proposal", "story": story_id, "question": proposal["reason"],
                "next_action": "confirm or reject the cancellation",
            })
    for epic_id, epic in sorted(epics.items()):
        if epic["status"] == "awaiting-acceptance":
            decision_queue.append({
                "kind": "epic-acceptance", "epic": epic_id,
                "question": f"accept epic {epic_id} ({epic['title']}) against its done-when?",
                "next_action": "run the epic checkpoint and confirm",
            })
        proposal = epic.get("park_proposal")
        if isinstance(proposal, dict):
            decision_queue.append({
                "kind": "park-proposal", "epic": epic_id,
                "question": f"park epic {epic_id} ({epic['title']})?",
                "next_action": proposal["resume"],
            })

    chains = critical_paths(stories, stream_of)

    projection_streams = []
    for stream in streams:
        counts = {"planned": 0, "ready": 0, "in-progress": 0, "review": 0,
                  "built": 0, "done": 0, "cancelled": 0}
        for story_id, story in stories.items():
            if stream_of.get(story_id) == stream["id"]:
                counts[derived[story_id][0]] += 1
        projection_streams.append({
            "id": stream["id"], "title": stream["title"], "status": stream["status"],
            "epics": list(stream["epics"]), "counts": counts,
            "critical_path": chains.get(stream["id"], []),
        })

    projection_epics = []
    for stream in streams:
        for epic_id in stream["epics"]:
            epic = epics.get(epic_id)
            if epic is None:
                continue
            projection_epics.append({
                "id": epic_id, "stream": stream["id"], "title": epic["title"],
                "outcome": epic.get("outcome", ""), "status": epic["status"],
                "done_when": list(epic.get("done_when", [])),
                "covers": list(epic.get("covers", [])),
                "order": list(epic.get("order", [])), "needs": list(epic.get("needs", [])),
                "acceptance": epic.get("acceptance"), "parked": epic.get("parked"),
            })

    projection_stories = []
    for story_id, story in sorted(stories.items()):
        if story_id not in stream_of:
            continue
        state, _, _, _ = derived[story_id]
        claim = claims.get(str(story_id))
        entry = {
            "id": story_id, "epic": story["epic"], "stream": stream_of[story_id],
            "type": story["type"], "title": story["title"],
            "status": story["status"], "state": state, "owner": story.get("owner"),
            "after": list(story.get("after", [])), "covers": list(story.get("covers", [])),
            "risk": story.get("risk", ""),
            "hitl": story.get("hitl", False),
            "plan_checkpoint": story.get("plan_checkpoint", False),
            "done_checkpoint": story.get("done_checkpoint", False),
            "blocked": story.get("blocked"),
            "receipts": story.get("receipts", {}),
            "baseline_sha": story.get("baseline_sha"), "branch": story.get("branch"),
            "pr": story.get("pr"), "merged_sha": story.get("merged_sha"),
            "claim": (
                {"live": True, "owner": claim.get("owner"), "paths": list(claim.get("paths", [])),
                 "claimed_at": claim.get("claimed_at")}
                if claim else {"live": False}
            ),
            "blocks": sorted(blocks.get(story_id, [])),
            "history": list(story.get("history", [])),
            "findings": list(story.get("findings", [])),
        }
        for key in ("sprint", "scope", "source_key"):
            if key in story:
                entry[key] = story[key]
        for key in sorted(story):
            if key not in entry and key not in (
                "version", "cancel_proposal", "cancellation"
            ):
                entry[key] = story[key]
        projection_stories.append(entry)

    payload = {
        "streams": projection_streams,
        "epics": projection_epics,
        "stories": projection_stories,
        "frontier": {"ready": frontier_ready, "waiting_on_prereq": waiting},
        "blockers": blockers,
        "diagnostics": {
            "unpinned_gates": unpinned_gates,
            "undeclared_after": undeclared_after,
            "order_conflicts": order_conflicts,
            "inconsistencies": inconsistencies,
        },
        "decision_queue": decision_queue,
        "problems": problems,
    }
    return payload


def build(workspace: Path, config=None):
    """Regenerate roadmap.json and dashboard.html from the records; locked."""
    config = board_config(workspace) if config is None else config
    directory = board_dir(workspace, config)
    if not (directory / "streams.json").is_file():
        raise BoardError(
            f"no board at {config['dir']}; run `roadmap.py init` or `roadmap.py derive` first"
        )
    with board_locked(workspace):
        payload = compute_roadmap(workspace, config, directory)
        roadmap_path = directory / "roadmap.json"
        revision = 1
        generated_at = now()
        existing = read_record(roadmap_path)
        if existing is not None:
            prior = {key: value for key, value in existing.items()
                     if key not in ("revision", "generated_at")}
            candidate = {"version": 1, "generated": {
                "by": GENERATED_BY, "command": GENERATED_COMMAND, "note": GENERATED_NOTE,
            }, **payload}
            if prior == candidate:
                revision = existing.get("revision", 0)
                generated_at = existing.get("generated_at", generated_at)
            else:
                revision = existing.get("revision", 0) + 1
        document = {
            "version": 1,
            "generated": {"by": GENERATED_BY, "command": GENERATED_COMMAND, "note": GENERATED_NOTE},
            "generated_at": generated_at,
            "revision": revision,
            **payload,
        }
        state_module().atomic_json(roadmap_path, document)
        html = dashboard_module().render_html(document)
        dashboard_path = directory / "dashboard.html"
        if not dashboard_path.is_file() or dashboard_path.read_text() != html:
            state_module().atomic_text(dashboard_path, html)
    stories = len(payload["stories"])
    problems = len(payload["problems"])
    diagnostics = sum(len(value) for value in payload["diagnostics"].values())
    print(
        f"board: roadmap revision {revision} "
        f"({stories} stories, {len(payload['streams'])} streams; "
        f"{problems} problems, {diagnostics} diagnostics)"
    )
    return revision


def init_board(workspace: Path):
    config = board_config(workspace)
    directory = board_dir(workspace, config)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "epics").mkdir(exist_ok=True)
    (directory / "stories").mkdir(exist_ok=True)
    if not (directory / "streams.json").exists():
        write_record(directory / "streams.json", {"version": 1, "streams": []})
    if not (directory / "meta.json").exists():
        write_record(directory / "meta.json", {"version": 1, "next_story_id": 1, "next_epic_id": 1})
    return directory


def maybe_build(workspace: Path, config):
    if config["regenerate"] == "on-write":
        build(workspace, config=config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "derive", "update", "epic", "build"])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path)
    parser.add_argument("--story")
    parser.add_argument("--epic")
    parser.add_argument("--actor", choices=["worker", "orchestrator", "human"])
    parser.add_argument("--owner")
    parser.add_argument("--status")
    parser.add_argument("--receipt", action="append")
    parser.add_argument("--sha")
    parser.add_argument("--evidence")
    parser.add_argument("--block")
    parser.add_argument("--unblock", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--block-owner")
    parser.add_argument("--next-action")
    parser.add_argument("--finding")
    parser.add_argument("--decision")
    parser.add_argument("--resume")
    args = parser.parse_args()
    root = args.workspace.resolve()
    try:
        if args.command == "init":
            directory = init_board(root)
            print(f"board: initialized at {directory.relative_to(root)}")
            return 0
        if args.command == "derive":
            if args.source is None:
                parser.error("derive needs --source")
            epics, stories = derive(root, args.source)
            config = board_config(root)
            maybe_build(root, config)
            print(f"board: derived {epics} epics, {stories} stories from the planning source")
            return 0
        if args.command == "build":
            build(root)
            return 0
        if args.command == "update":
            if args.story is None or args.actor is None:
                parser.error("update needs --story and --actor")
            record = update_story(root, args)
            maybe_build(root, args._validated_config if hasattr(args, "_validated_config") else board_config(root))
            print(f"board: story {record['id']} updated ({record['status']})")
            return 0
        if args.command == "epic":
            if args.epic is None or args.actor is None or args.status is None:
                parser.error("epic needs --epic, --actor and --status")
            record = epic_update(root, args)
            maybe_build(root, args._validated_config if hasattr(args, "_validated_config") else board_config(root))
            print(f"board: epic {record['id']} updated ({record['status']})")
            return 0
        return 2
    except BoardError as exc:
        print(f"board: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"board: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
