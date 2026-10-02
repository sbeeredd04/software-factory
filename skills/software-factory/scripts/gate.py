"""Validate evidence manifests structurally.

Checks subject binding, reviewer independence, phase-required checks, pass
statuses, strict integer exit codes, artifact containment, deploy freshness
and approved exceptions. It reads evidence and configuration data only: it
never attests artifact truth and never runs anything.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA1 = re.compile(r"[0-9a-f]{40}")
DEFAULT_REQUIRED = {
    "premerge": ("tests", "eval", "review", "ci"),
    "complete": ("tests", "eval", "review", "ci", "deploy"),
}
DEPLOY_CHECK = "deploy"


def configured_required(config_path, phase):
    """Resolve the required check names; fail closed on any unusable config."""
    if config_path is None:
        return list(DEFAULT_REQUIRED[phase])
    try:
        data = json.loads(Path(config_path).read_text())
    except (OSError, ValueError):
        raise ValueError(f"config unreadable or not JSON: {Path(config_path).name}")
    if not isinstance(data, dict):
        raise TypeError("config must be an object")
    section = data.get("verification")
    if not isinstance(section, dict):
        raise TypeError("config: verification section missing")
    names = section.get("required_checks")
    if (
        not isinstance(names, list)
        or not names
        or not all(isinstance(name, str) and name for name in names)
    ):
        raise ValueError("config: verification.required_checks must be a nonempty list of check names")
    if len(set(names)) != len(names):
        raise ValueError("config: verification.required_checks has duplicate names")
    required = list(names)
    if phase == "complete" and DEPLOY_CHECK not in required:
        required.append(DEPLOY_CHECK)
    return required


def validate(report, root, sha, phase="complete", required=None):
    errors = []
    if required is None:
        required = list(DEFAULT_REQUIRED[phase])
    if not SHA1.fullmatch(sha or ""):
        return ["expected a full Git SHA"]
    if not isinstance(report, dict):
        return ["invalid evidence manifest"]
    if report.get("subject_sha") != sha:
        return ["report SHA does not match subject"]
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return ["missing checks"]
    author, reviewer = report.get("author"), report.get("reviewer")
    if not author or not reviewer or author == reviewer:
        errors.append("independent reviewer required")
    for name in required:
        check = checks.get(name)
        if not isinstance(check, dict):
            errors.append(f"{name}: missing")
            continue
        if check.get("status") == "not_applicable":
            if check.get("subject_sha") != sha:
                errors.append(f"{name}: stale exception")
            if not check.get("approved_by") or not check.get("reason") or not check.get("decision_ref"):
                errors.append(f"{name}: unapproved exception")
            continue
        if check.get("status") != "pass" or check.get("subject_sha") != sha:
            errors.append(f"{name}: failed, incomplete or stale")
            continue
        if check.get("command") or "exit_code" in check:
            code = check.get("exit_code")
            if type(code) is not int or code != 0:
                errors.append(f"{name}: exit code not successful")
        artifact = check.get("artifact")
        if not isinstance(artifact, str) or Path(artifact).is_absolute():
            errors.append(f"{name}: local artifact reference required")
            continue
        target = (root / artifact).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            errors.append(f"{name}: artifact missing or outside evidence root")
        if name == DEPLOY_CHECK and check.get("deployed_sha") != sha:
            errors.append(f"{DEPLOY_CHECK}: deployed SHA mismatch")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--phase", choices=tuple(DEFAULT_REQUIRED), default="complete")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        required = configured_required(args.config, args.phase)
        report = json.loads(args.report.read_text())
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc) or "invalid evidence manifest")
        return 1
    errors = validate(report, args.root.resolve(), args.sha, args.phase, required)
    print(
        "\n".join(errors)
        if errors
        else "Evidence structure complete; independently verify artifact contents."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
