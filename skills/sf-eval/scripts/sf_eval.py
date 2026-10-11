#!/usr/bin/env python3
"""sf-eval: the factory's standard-library eval runner.

Runs the eval cases a project declares in its eval plan and writes the
receipts the factory's evidence gate cites.

- ``run`` executes one cost-tiered mode (``quick`` per story, ``epic``,
  ``premerge``, ``canary``) over the plan's cases and writes
  ``<runs-dir>/<run-id>/evals/receipt.json``, one JSON file per case, and
  small text artifacts for failures only.
- ``verify`` re-checks a receipt: its ``self_sha256`` must reproduce and its
  verdict must be ``pass``.
- ``verify-manifest`` checks that a gate manifest's ``eval`` block cites a
  real, untampered, green receipt, or carries an approved override record.
- ``override`` records a human override (who/when/why) on a receipt and
  re-hashes it.

The runner executes the deterministic ladder rungs natively (``state``,
``command``, ``http`` against case-declared local URLs, ``golden``) and
shells out only to the harness command a surface declares (``browser``,
``judge``). It is standard-library only, works offline, installs nothing,
emits no telemetry and never calls a model or an agent CLI. A missing
harness, renderer or tool is reported as ``unverified`` with a nonzero
result, never as a pass.

Exit codes: 0 on a green run or a successful verification, 1 on a failure
or a refused verification, 2 on a usage or plan error (one ``sf_eval:``
message on stderr, no partial receipts).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "sf-eval/1"
GRADE_TYPES = ("state", "command", "http", "browser", "golden", "judge")
NATIVE_GRADES = ("state", "command", "http", "golden")
KINDS = ("fail_to_pass", "pass_to_pass")
MODES = ("quick", "epic", "premerge", "canary")
CASE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z0-9]+-[0-9]{3}$")
CONSISTENCY_RE = re.compile(r"^(pass[@^]k|majority)$")
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_RUNS_DIR = ".software-factory/runs"
COMMAND_TIMEOUT_SEC = 300
HTTP_TIMEOUT_SEC = 15
MAX_OUTPUT_ARTIFACT_BYTES = 4096
MAX_BODY_ARTIFACT_BYTES = 8192
MAX_DIFF_LINES = 200
DEFAULT_RETRY_CAP = 3

PASS = "pass"
FAIL = "fail"
UNVERIFIED = "unverified"


class PlanError(Exception):
    """The eval plan is structurally unusable; the runner fails closed."""


class Unverified(Exception):
    """The case cannot be graded in this environment; never counted a pass."""


def utc_now():
    """Current UTC time in the receipt timestamp format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def receipt_digest(obj):
    """The sha256 self-hash: the receipt with ``self_sha256`` excluded.

    Canonicalization is UTF-8 JSON with sorted keys and compact separators;
    removing the field and re-digesting must reproduce the stored value.
    """
    payload = {key: value for key, value in obj.items() if key != "self_sha256"}
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def atomic_write_json(path, obj):
    """Write JSON atomically (tempfile plus os.replace), sorted and indented."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(blob)
    os.replace(tmp, path)


def write_artifact(artifacts_dir, name, text, limit):
    """Write a bounded text failure artifact; return its run-relative path."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / name
    path.write_text(text[:limit], encoding="utf-8")
    return str(Path("artifacts") / path.parent.name / name)


# -- plan loading -----------------------------------------------------------


def _require(condition, message):
    if not condition:
        raise PlanError(message)


def validate_case(case, surface_ids, seen_ids):
    """Fail closed on any case the runner cannot trace or grade."""
    _require(isinstance(case, dict), "plan: every case must be an object")
    case_id = case.get("id")
    _require(
        isinstance(case_id, str) and CASE_ID_RE.fullmatch(case_id),
        f"plan: case id {case_id!r} must match <SURFACE>-<STORY>-<NN> "
        "(e.g. FE-CART-001)",
    )
    _require(case_id not in seen_ids, f"plan: duplicate case id {case_id}")
    seen_ids.add(case_id)
    _require(case.get("story"), f"plan: case {case_id} has no story")
    _require(case.get("criterion"), f"plan: case {case_id} has no criterion")
    _require(
        case.get("kind") in KINDS,
        f"plan: case {case_id} kind must be one of {', '.join(KINDS)}",
    )
    _require(
        case.get("surface") in surface_ids,
        f"plan: case {case_id} names an undeclared surface",
    )
    grade = case.get("grade")
    _require(isinstance(grade, dict), f"plan: case {case_id} has no grade")
    gtype = grade.get("type")
    _require(
        gtype in GRADE_TYPES,
        f"plan: case {case_id} grade type {gtype!r} is not in the closed "
        f"ladder ({', '.join(GRADE_TYPES)})",
    )
    required = {
        "state": ("path",),
        "command": ("run",),
        "http": ("request",),
        "golden": ("golden",),
    }
    for key in required.get(gtype, ()):
        _require(grade.get(key), f"plan: case {case_id} grade needs '{key}'")
    if gtype == "golden":
        _require(
            bool(grade.get("command")) != bool(grade.get("path")),
            f"plan: case {case_id} golden grade needs exactly one of "
            "'command' or 'path'",
        )
    tier = case.get("tier")
    if tier is not None:
        _require(
            isinstance(tier, list)
            and all(item in MODES for item in tier),
            f"plan: case {case_id} tier must list run modes {MODES}",
        )
    if gtype == "judge":
        _require(
            case.get("nondeterministic") is True,
            f"plan: judge case {case_id} must be marked nondeterministic",
        )
    if case.get("nondeterministic"):
        policy = grade.get("consistency")
        _require(
            policy is None or CONSISTENCY_RE.fullmatch(str(policy)),
            f"plan: case {case_id} consistency must be pass@k, pass^k or "
            "majority",
        )


def load_plan(path):
    """Read and structurally validate the eval plan; fail closed."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"plan unreadable or not JSON: {exc}") from exc
    _require(isinstance(data, dict), "plan: top level must be an object")
    _require(data.get("version") == 1, "plan: version must be 1")
    surfaces = {}
    for surface in data.get("surfaces") or []:
        _require(
            isinstance(surface, dict) and surface.get("id"),
            "plan: every surface needs an id",
        )
        surfaces[surface["id"]] = surface
    _require(surfaces, "plan: at least one surface is required")
    cases = data.get("cases")
    _require(isinstance(cases, list), "plan: cases must be a list")
    seen_ids = set()
    for case in cases:
        validate_case(case, surfaces, seen_ids)
    return data


# -- case selection (cost-tiered modes) -------------------------------------


def select_cases(plan, mode, story=None, epic=None):
    """Split the plan into (runnable, skipped) for the given mode."""
    cases = plan["cases"]
    if mode == "quick":
        _require(story, "quick mode needs --story")
        scoped = [
            c for c in cases
            if c.get("story") == story or c.get("suite") == "smoke"
        ]
    elif mode == "epic":
        _require(epic, "epic mode needs --epic")
        scoped = [
            c for c in cases
            if c.get("epic") == epic or c.get("kind") == "pass_to_pass"
        ]
    elif mode == "premerge":
        scoped = list(cases)
    else:  # canary
        scoped = [c for c in cases if c.get("suite") in ("smoke", "canary")]
    mode_cfg = (plan.get("modes") or {}).get(mode) or {}
    allow = mode_cfg.get("allow_grades")
    if allow is None and mode == "quick":
        allow = [g for g in GRADE_TYPES if g != "judge"]
    runnable, skipped = [], {}
    for case in scoped:
        if mode not in case.get("tier", list(MODES)):
            skipped[case["id"]] = f"tier does not include {mode}"
        elif allow is not None and case["grade"]["type"] not in allow:
            skipped[case["id"]] = f"grade not allowed in {mode} mode"
        elif mode == "quick" and case.get("nondeterministic"):
            skipped[case["id"]] = "nondeterministic cases run at epic/premerge"
        else:
            runnable.append(case)
    return runnable, skipped


def aggregate_trials(statuses, policy):
    """Collapse trial statuses under a consistency policy (small k)."""
    passes = statuses.count(PASS)
    if policy == "pass@k":
        outcome = PASS if passes >= 1 else FAIL
    elif policy == "pass^k":
        outcome = PASS if passes == len(statuses) else FAIL
    elif policy == "majority":
        outcome = PASS if passes * 2 > len(statuses) else FAIL
    else:
        raise PlanError(f"unknown consistency policy {policy!r}")
    if outcome != PASS and UNVERIFIED in statuses:
        return UNVERIFIED
    return outcome


# -- deterministic graders ---------------------------------------------------


def dig(data, dotted):
    """Walk a dotted path with optional [index] steps ('items[0].sku')."""
    node = data
    for part in dotted.split("."):
        match = re.fullmatch(r"([^\[\]]+)((?:\[\d+\])*)", part)
        if not match:
            raise KeyError(dotted)
        key, indexes = match.groups()
        if not isinstance(node, dict) or key not in node:
            raise KeyError(dotted)
        node = node[key]
        for index in re.findall(r"\[(\d+)\]", indexes):
            node = node[int(index)]
    return node


def _resolve_inside(root, rel):
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise Unverified(f"path {rel!r} escapes the project root")
    return target


def check_state(case, root, _artifacts_dir, _env, _surface):
    """Rung 1: assert the end state of a file directly."""
    grade = case["grade"]
    target = _resolve_inside(root, grade["path"])
    want_exists = bool(grade.get("exists", True))
    exists = target.is_file()
    expected = ["exists" if want_exists else "absent"]
    problems = []
    if exists != want_exists:
        problems.append("exists" if exists else "missing")
    if exists and want_exists:
        text = target.read_text(encoding="utf-8", errors="replace")
        for needle in grade.get("contains", []):
            expected.append(f"contains {needle!r}")
            if needle not in text:
                problems.append(f"missing {needle!r}")
        assertions = grade.get("json", {})
        if assertions:
            try:
                data = json.loads(text)
            except ValueError:
                problems.append("file is not JSON")
                data = None
        for dotted, want in assertions.items():
            expected.append(f"{dotted} = {want!r}")
            try:
                got = dig(data, dotted)
            except (KeyError, IndexError, TypeError):
                problems.append(f"{dotted} absent")
            else:
                if got != want:
                    problems.append(f"{dotted}: got {got!r}")
    actual = "; ".join(problems) if problems else "as expected"
    if not exists and want_exists:
        actual = "missing"
    return {
        "ok": not problems,
        "expected": "; ".join(expected),
        "actual": actual,
        "detail": "",
        "artifacts": [],
    }


def _run_shell(command, root, env):
    try:
        return subprocess.run(
            command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def check_command(case, root, artifacts_dir, env, _surface):
    """Rung 2: run the declared command; assert exit code and output."""
    grade = case["grade"]
    expect = grade.get("expect", {})
    want_exit = expect.get("exit", 0)
    proc = _run_shell(grade["run"], root, env)
    expected = f"exit {want_exit}"
    pattern = expect.get("output_matches")
    if pattern:
        expected += f"; output matches {pattern!r}"
    if proc is None:
        return {
            "ok": False,
            "expected": expected,
            "actual": f"timeout after {COMMAND_TIMEOUT_SEC}s",
            "detail": "command timed out",
            "artifacts": [],
        }
    combined = (proc.stdout or "") + (proc.stderr or "")
    problems = []
    if proc.returncode != want_exit:
        problems.append(f"exit {proc.returncode}")
    if pattern and not re.search(pattern, combined):
        problems.append("output pattern not found")
    artifacts = []
    if problems:
        artifacts.append(
            write_artifact(
                artifacts_dir, "output.txt",
                combined[-MAX_OUTPUT_ARTIFACT_BYTES:], MAX_OUTPUT_ARTIFACT_BYTES,
            )
        )
    return {
        "ok": not problems,
        "expected": expected,
        "actual": "; ".join(problems) if problems else f"exit {proc.returncode}",
        "detail": "",
        "artifacts": artifacts,
    }


def _resolve_url(request, surface, env):
    url = request.get("url")
    if not url:
        path = request.get("path")
        if not path:
            raise Unverified("http case needs a 'url' or a 'path'")
        base_var = (surface or {}).get("base_url_env")
        base = env.get(base_var) if base_var else None
        if not base:
            raise Unverified(f"base URL env {base_var!r} is not set")
        url = base.rstrip("/") + "/" + str(path).lstrip("/")
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise Unverified(
            f"refused non-local URL host {host!r}; the runner probes only "
            "local URLs the case itself names"
        )
    return url


def _http_request(request, surface, env):
    url = _resolve_url(request, surface, env)
    body = request.get("body")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", **(request.get("headers") or {})}
    req = urllib.request.Request(
        url, data=data, headers=headers, method=request.get("method", "GET")
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise ProbeDown(str(exc)) from exc


class ProbeDown(Exception):
    """The probe target did not answer; a genuine failure, not unverified."""


def _http_assertions(expect, status, body):
    problems = []
    want_status = expect.get("status", 200)
    if status != want_status:
        problems.append(f"status {status} != {want_status}")
    for needle in expect.get("contains", []):
        if needle not in body:
            problems.append(f"body missing {needle!r}")
    assertions = expect.get("json", {})
    if assertions:
        try:
            data = json.loads(body)
        except ValueError:
            problems.append("body is not JSON")
            data = None
        for dotted, want in assertions.items():
            try:
                got = dig(data, dotted)
            except (KeyError, IndexError, TypeError):
                problems.append(f"json {dotted} absent")
            else:
                if got != want:
                    problems.append(f"json {dotted}: got {got!r}")
    return want_status, problems


def check_http(case, root, artifacts_dir, env, surface):
    """Rung 3: HTTP probe against a case-declared local URL."""
    grade = case["grade"]
    try:
        status, body = _http_request(grade["request"], surface, env)
        want_status, problems = _http_assertions(
            grade.get("expect", {}), status, body
        )
        if not problems and grade.get("then"):
            follow = grade["then"]
            status, body = _http_request(follow["request"], surface, env)
            want_status, problems = _http_assertions(
                follow.get("expect", {}), status, body
            )
    except ProbeDown as exc:
        return {
            "ok": False,
            "expected": "reachable local URL",
            "actual": "connection failed",
            "detail": str(exc),
            "artifacts": [],
        }
    artifacts = []
    if problems:
        dump = f"status: {status}\n\n{body[:MAX_BODY_ARTIFACT_BYTES]}"
        artifacts.append(
            write_artifact(
                artifacts_dir, "response.txt", dump, MAX_BODY_ARTIFACT_BYTES * 2
            )
        )
    return {
        "ok": not problems,
        "expected": f"status {want_status} plus body assertions",
        "actual": "; ".join(problems) if problems else f"status {status}",
        "detail": "",
        "artifacts": artifacts,
    }


def check_golden(case, root, artifacts_dir, env, _surface):
    """Rung 5: diff produced output against the approved golden."""
    grade = case["grade"]
    golden_rel = grade["golden"]
    golden_path = _resolve_inside(root, golden_rel)
    if not golden_path.is_file():
        raise Unverified(f"golden {golden_rel!r} not found")
    if grade.get("command"):
        proc = _run_shell(grade["command"], root, env)
        if proc is None:
            raise Unverified("golden producer command timed out")
        if proc.returncode != 0:
            raise Unverified(
                f"golden producer exited {proc.returncode}: "
                f"{(proc.stderr or '')[-200:]}"
            )
        produced = proc.stdout or ""
    else:
        produced_path = _resolve_inside(root, grade["path"])
        if not produced_path.is_file():
            return {
                "ok": False,
                "expected": f"produced file {grade['path']}",
                "actual": "produced file missing",
                "detail": "",
                "artifacts": [],
            }
        produced = produced_path.read_text(encoding="utf-8", errors="replace")
    golden = golden_path.read_text(encoding="utf-8", errors="replace")
    if produced == golden:
        return {
            "ok": True,
            "expected": f"matches golden {golden_rel}",
            "actual": "identical",
            "detail": "",
            "artifacts": [],
        }
    diff = "\n".join(
        list(
            difflib.unified_diff(
                golden.splitlines(), produced.splitlines(),
                fromfile="golden", tofile="actual",
            )
        )[:MAX_DIFF_LINES]
    )
    return {
        "ok": False,
        "expected": f"matches golden {golden_rel}",
        "actual": "differs",
        "detail": "",
        "artifacts": [write_artifact(artifacts_dir, "diff.txt", diff + "\n",
                                     MAX_BODY_ARTIFACT_BYTES)],
    }


def check_via_harness(case, root, artifacts_dir, env, surface):
    """Rungs 4 and 6: shell out to the surface's declared harness command.

    The harness receives the case JSON path and a result-file path and must
    write ``{"status": "pass"|"fail", "actual": ..., "detail": ...}``. The
    runner never grades subjectivity itself; a missing harness is
    ``unverified``, never a pass.
    """
    harness = (surface or {}).get("harness") or {}
    run_cmd = harness.get("run")
    gtype = case["grade"]["type"]
    if not run_cmd:
        raise Unverified(f"no harness declared for grade {gtype!r}")
    with tempfile.TemporaryDirectory(prefix="sf-eval-") as tmp:
        case_file = Path(tmp) / "case.json"
        result_file = Path(tmp) / "result.json"
        case_file.write_text(
            json.dumps({"schema": SCHEMA, "case": case, "surface": surface},
                       indent=2),
            encoding="utf-8",
        )
        argv = shlex.split(run_cmd) + [str(case_file), str(result_file)]
        try:
            proc = subprocess.run(
                argv, cwd=root, capture_output=True, text=True,
                timeout=COMMAND_TIMEOUT_SEC, env=env, check=False,
            )
        except FileNotFoundError as exc:
            raise Unverified(f"harness not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise Unverified("harness timed out") from exc
        if not result_file.is_file():
            tail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
            raise Unverified(f"harness wrote no result file ({tail.strip()})")
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise Unverified("harness result is not JSON") from exc
    status = data.get("status")
    if status not in (PASS, FAIL):
        raise Unverified(f"harness reported unknown status {status!r}")
    artifacts = []
    if status == FAIL:
        combined = (proc.stdout or "") + (proc.stderr or "")
        if combined.strip():
            artifacts.append(
                write_artifact(artifacts_dir, "harness-output.txt",
                               combined[-MAX_OUTPUT_ARTIFACT_BYTES:],
                               MAX_OUTPUT_ARTIFACT_BYTES)
            )
    return {
        "ok": status == PASS,
        "expected": "harness pass",
        "actual": str(data.get("actual", status)),
        "detail": str(data.get("detail", "")),
        "artifacts": artifacts,
    }


GRADERS = {
    "state": check_state,
    "command": check_command,
    "http": check_http,
    "golden": check_golden,
    "browser": check_via_harness,
    "judge": check_via_harness,
}


def grade_case(case, surfaces, root, artifacts_dir, env):
    """Grade one case once; translate environment gaps into ``unverified``."""
    surface = surfaces.get(case.get("surface"))
    grader = GRADERS[case["grade"]["type"]]
    try:
        outcome = grader(case, root, artifacts_dir, env, surface)
    except Unverified as exc:
        return {
            "status": UNVERIFIED,
            "expected": "a runnable grader",
            "actual": "unverified",
            "detail": str(exc),
            "artifacts": [],
        }
    outcome["status"] = PASS if outcome.pop("ok") else FAIL
    return outcome


# -- receipts ----------------------------------------------------------------


def git_sha(root):
    """Best-effort read-only HEAD lookup; 'unknown' outside a git repo."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else "unknown"


def mint_run_id(runs_dir, mode):
    """A stable, unique run id: r-<UTC timestamp>-<mode>[-n]."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"r-{stamp}-{mode}"
    suffix = 1
    while (runs_dir / run_id).exists():
        suffix += 1
        run_id = f"r-{stamp}-{mode}-{suffix}"
    return run_id


def prior_failure_count(runs_dir, case_id):
    """How many earlier run receipts record this case as failed."""
    count = 0
    for receipt_path in sorted(runs_dir.glob("*/evals/receipt.json")):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (receipt.get("cases") or {}).get(case_id) == FAIL:
            count += 1
    return count


# -- subcommands --------------------------------------------------------------


def cmd_run(args):
    """Execute one cost-tiered mode and write receipts."""
    plan = load_plan(args.plan)
    runnable, skipped = select_cases(plan, args.mode, args.story, args.epic)
    surfaces = {s["id"]: s for s in plan["surfaces"]}
    args.started = utc_now()
    mode_cfg = (plan.get("modes") or {}).get(args.mode) or {}
    # Mint the run id before grading so failure artifacts land in place.
    run_id = mint_run_id(args.runs_dir, args.mode)
    evals_dir = args.runs_dir / run_id / "evals"
    results = []
    for case in runnable:
        artifacts_dir = evals_dir / "artifacts" / case["id"]
        grade = case["grade"]
        trials = 1
        policy = None
        if case.get("nondeterministic"):
            trials = int(grade.get("trials")
                         or mode_cfg.get("nondeterministic_trials") or 1)
            policy = grade.get("consistency") or mode_cfg.get("consistency") or "pass@k"
        outcomes = [
            grade_case(case, surfaces, args.project_root, artifacts_dir,
                       dict(os.environ))
            for _ in range(max(1, trials))
        ]
        if policy and trials > 1:
            statuses = [o["status"] for o in outcomes]
            final = dict(outcomes[-1])
            final["status"] = aggregate_trials(statuses, policy)
            final["trials"] = {
                "count": trials,
                "consistency": policy,
                "statuses": statuses,
            }
        else:
            final = outcomes[-1]
        results.append((case, final))
    receipt, out_dir = write_run(
        plan, args.plan, args, run_id, evals_dir, skipped, results
    )
    print(f"run {receipt['run_id']}: verdict {receipt['verdict']} "
          f"({receipt['totals']['passed']} passed, "
          f"{receipt['totals']['failed']} failed, "
          f"{receipt['totals']['unverified']} unverified, "
          f"{receipt['totals']['quarantined']} quarantined, "
          f"{receipt['totals']['skipped']} skipped)")
    print(f"receipt: {out_dir / 'receipt.json'}")
    return 0 if receipt["verdict"] == PASS else 1


def write_run(plan, plan_path, args, run_id, evals_dir, skipped, results):
    """Write the per-case files and the run receipt; return (receipt, dir)."""
    cases_dir = evals_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    retry_cap = int(
        (plan.get("routing") or {}).get("retry_cap_per_case", DEFAULT_RETRY_CAP)
    )
    cases_map = {}
    quarantined = []
    for case, outcome in results:
        record = {
            "schema": SCHEMA,
            "id": case["id"],
            "story": case.get("story"),
            "epic": case.get("epic"),
            "suite": case.get("suite"),
            "kind": case.get("kind"),
            "criterion": case.get("criterion"),
            "surface": case.get("surface"),
            "grade_type": case["grade"]["type"],
            "mode": args.mode,
            "status": outcome["status"],
            "expected": outcome.get("expected", ""),
            "actual": outcome.get("actual", ""),
            "detail": outcome.get("detail", ""),
            "artifacts": outcome.get("artifacts", []),
            "quarantined": bool(case.get("quarantined")),
        }
        if case.get("nondeterministic") and outcome.get("trials"):
            record["trials"] = outcome["trials"]
        if outcome["status"] == FAIL:
            priors = prior_failure_count(args.runs_dir, case["id"])
            suspect = priors >= retry_cap
            record["triage_hint"] = {
                "route": "eval-fix-review" if suspect else "code-fix",
                "suspect_eval": suspect,
                "prior_failures": priors,
            }
        if case.get("quarantined"):
            quarantined.append(case["id"])
        cases_map[case["id"]] = outcome["status"]
        atomic_write_json(cases_dir / f"{case['id']}.json", record)
    blocking = [
        outcome["status"]
        for case, outcome in results
        if not case.get("quarantined")
    ]
    verdict = (
        FAIL if FAIL in blocking
        else UNVERIFIED if UNVERIFIED in blocking
        else PASS
    )
    receipt = {
        "schema": SCHEMA,
        "run_id": run_id,
        "mode": args.mode,
        "story_ids": sorted({c.get("story") for c, _ in results}),
        "epic_ids": sorted({c.get("epic") for c, _ in results if c.get("epic")}),
        "started": args.started,
        "finished": utc_now(),
        "git_sha": git_sha(args.project_root),
        "config_sha256": hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
        "command": "sf_eval.py " + " ".join(shlex.quote(a) for a in sys.argv[1:]),
        "cases": cases_map,
        "skipped": skipped,
        "quarantined_cases": quarantined,
        "totals": {
            "passed": sum(1 for s in cases_map.values() if s == PASS),
            "failed": sum(1 for s in cases_map.values() if s == FAIL),
            "unverified": sum(1 for s in cases_map.values() if s == UNVERIFIED),
            "quarantined": len(quarantined),
            "skipped": len(skipped),
        },
        "verdict": verdict,
        "overrides": [],
    }
    receipt["self_sha256"] = receipt_digest(receipt)
    atomic_write_json(evals_dir / "receipt.json", receipt)
    return receipt, evals_dir


def _load_receipt(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"receipt unreadable: {exc}")
        return None
    return data


def verify_receipt(path):
    """Re-digest the receipt and require a pass verdict. Returns errors."""
    data = _load_receipt(path)
    if data is None:
        return [f"receipt unreadable: {path}"]
    stored = data.get("self_sha256")
    if not stored:
        return ["receipt has no self_sha256"]
    if receipt_digest(data) != stored:
        return ["receipt digest mismatch: the receipt was altered"]
    verdict = data.get("verdict")
    if verdict != PASS:
        return [f"receipt verdict is {verdict!r}, not 'pass'"]
    return []


def cmd_verify(args):
    """Verify one receipt's self-hash and verdict."""
    errors = verify_receipt(args.receipt)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"receipt verified: {args.receipt}")
    return 0


def _eval_block(manifest):
    if isinstance(manifest.get("eval"), dict):
        return manifest["eval"]
    checks = manifest.get("checks")
    if isinstance(checks, dict) and isinstance(checks.get("eval"), dict):
        return checks["eval"]
    return None


def cmd_verify_manifest(args):
    """Verify a gate manifest's eval citation against its receipt."""
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"manifest unreadable: {exc}")
        return 1
    block = _eval_block(manifest)
    if block is None:
        print("manifest has no eval block")
        return 1
    if block.get("status") == "not_applicable":
        override = block.get("override") or {}
        missing = [
            key for key in ("who", "when", "reason") if not override.get(key)
        ]
        if missing:
            print(
                "eval not_applicable requires an approved override record "
                f"(missing: {', '.join(missing)})"
            )
            return 1
        print("eval not_applicable with a recorded override accepted")
        return 0
    root = args.root.resolve()
    rel = block.get("receipt")
    if not isinstance(rel, str) or not rel:
        print("eval block cites no receipt")
        return 1
    receipt_path = (root / rel).resolve()
    if not receipt_path.is_relative_to(root):
        print(f"eval receipt path escapes the root: {rel}")
        return 1
    if not receipt_path.is_file():
        print(f"eval receipt not found: {rel}")
        return 1
    errors = verify_receipt(receipt_path)
    if errors:
        print("\n".join(errors))
        return 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if block.get("self_sha256") != receipt["self_sha256"]:
        print("manifest cites a stale receipt digest")
        return 1
    if block.get("run_id") != receipt.get("run_id"):
        print("manifest run_id does not match the receipt")
        return 1
    if block.get("verdict") != receipt.get("verdict"):
        print("manifest verdict does not match the receipt")
        return 1
    if block.get("cases") != receipt.get("cases"):
        print("manifest case results do not match the receipt")
        return 1
    print(f"eval citation verified: {receipt['run_id']}")
    return 0


def cmd_override(args):
    """Record a human override (who/when/why) on a receipt and re-hash it."""
    data = _load_receipt(args.receipt)
    if data is None:
        return 1
    overrides = data.setdefault("overrides", [])
    overrides.append({"who": args.who, "when": args.when, "reason": args.reason})
    data["self_sha256"] = receipt_digest(data)
    atomic_write_json(Path(args.receipt), data)
    print(f"override recorded on {args.receipt}")
    return 0


def main(argv=None):
    """Parse the CLI and dispatch; plan errors fail closed with exit 2."""
    parser = argparse.ArgumentParser(
        prog="sf_eval.py",
        description="Standard-library eval runner for the sf-eval skill.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    run = sub.add_parser("run", help="run one cost-tiered eval mode")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--mode", choices=MODES, required=True)
    run.add_argument("--story")
    run.add_argument("--epic")
    run.add_argument("--project-root", type=Path, default=Path.cwd())
    run.add_argument("--runs-dir", type=Path)
    run.set_defaults(func=cmd_run)

    verify = sub.add_parser("verify", help="verify a receipt's self-hash")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.set_defaults(func=cmd_verify)

    manifest = sub.add_parser(
        "verify-manifest", help="verify a gate manifest's eval citation"
    )
    manifest.add_argument("--manifest", type=Path, required=True)
    manifest.add_argument("--root", type=Path, required=True)
    manifest.set_defaults(func=cmd_verify_manifest)

    override = sub.add_parser("override", help="record a human override")
    override.add_argument("--receipt", type=Path, required=True)
    override.add_argument("--who", required=True)
    override.add_argument("--reason", required=True)
    override.add_argument("--when", default=None)
    override.set_defaults(func=cmd_override)

    args = parser.parse_args(argv)
    if args.subcommand == "override":
        if not args.who.strip() or not args.reason.strip():
            print("sf_eval: override needs a nonempty --who and --reason",
                  file=sys.stderr)
            return 2
        if args.when is None:
            args.when = utc_now()
    if args.subcommand == "run":
        if not args.plan.is_file():
            print(f"sf_eval: plan not found: {args.plan}", file=sys.stderr)
            return 2
        if args.runs_dir is None:
            try:
                plan = json.loads(args.plan.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                plan = {}
            rel = plan.get("receipts_dir") or DEFAULT_RUNS_DIR
            args.runs_dir = args.project_root / rel
    try:
        return args.func(args)
    except PlanError as exc:
        print(f"sf_eval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
