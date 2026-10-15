"""Validate evidence manifests structurally.

Checks subject binding, reviewer independence, phase-required checks, pass
statuses, strict integer exit codes, artifact containment, deploy freshness
and approved exceptions. It reads evidence and configuration data only: it
never attests artifact truth and never runs anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime
from pathlib import Path

SHA1 = re.compile(r"[0-9a-f]{40}")
DEFAULT_REQUIRED = {
    "premerge": ("tests", "eval", "review", "ci"),
    "complete": ("tests", "eval", "review", "ci", "deploy"),
}
DEPLOY_CHECK = "deploy"
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_REQUIRED_CHECKS = 64
MAX_BOUND_ARTIFACT_BYTES = 8 * 1024 * 1024


def strict_json(content):
    """New gate data has no duplicate keys or non-finite numeric constants."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key in bound evidence")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("non-finite JSON constant in bound evidence")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number in bound evidence")
        return number

    try:
        return json.loads(content, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)
    except RecursionError as exc:
        raise ValueError("bound evidence exceeds JSON nesting budget") from exc


def structured_artifact(content, name):
    """A receipt cannot become opaque proof by renaming or changing encoding."""
    if content.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        raise ValueError("BOM-encoded evidence must be normalized to UTF-8 without BOM")
    if b"\x00" in content[:64]:
        for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            try:
                text = content.decode(encoding)
            except UnicodeError:
                continue
            if text.lstrip()[:1] in ("{", "["):
                raise ValueError("encoded structured evidence must be normalized to UTF-8")
    if name.lower().endswith(".json") or content.lstrip()[:1] in (b"{", b"["):
        return strict_json(content)
    return None


def valid_scope(scope):
    return (isinstance(scope, dict) and len(scope) == 1
            and next(iter(scope)) in ("story", "epic")
            and type(next(iter(scope.values()))) is int and next(iter(scope.values())) > 0)


def review_bundle(root, binding, scope_digest, legacy_children):
    """Independent reconciliation of a specific epic scope, not effect attestation."""
    if not isinstance(binding, dict):
        raise TypeError("epic acceptance needs independent reconciliation evidence")
    content = bound_read(root, binding.get("artifact"))
    if digest(content) != binding.get("sha256"):
        raise ValueError("epic evidence digest mismatch")
    report = strict_json(content)
    if (not isinstance(report, dict) or report.get("status") != "pass"
            or report.get("scope_sha256") != scope_digest
            or not all(isinstance(report.get(key), str) and report[key].strip() for key in ("author", "reviewer"))
            or report["author"] == report["reviewer"]
            or report.get("legacy_children", []) != legacy_children
            or any(type(value) is not int for value in report.get("legacy_children", []))):
        raise ValueError("epic reconciliation is stale, failed, incomplete or self-reviewed")
    artifacts = report.get("artifacts", [])
    if not isinstance(artifacts, list) or len(artifacts) > MAX_REQUIRED_CHECKS:
        raise ValueError("epic reconciliation artifact count exceeds its budget")
    detail = report.get("reconciliation")
    if not artifacts and (not isinstance(detail, str) or not detail.strip()):
        raise ValueError("epic evidence needs reconciliation detail or an outcome artifact")
    total = len(content)
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise TypeError("invalid reconciliation artifact")
        if total >= MAX_BOUND_ARTIFACT_BYTES:
            raise ValueError("epic reconciliation artifact reads exceeded their byte budget")
        proof = bound_read(root, artifact.get("artifact"),
                           limit=min(MAX_EVIDENCE_BYTES, MAX_BOUND_ARTIFACT_BYTES - total))
        total += len(proof)
        if not proof.strip() or total > MAX_BOUND_ARTIFACT_BYTES or digest(proof) != artifact.get("sha256"):
            raise ValueError("epic reconciliation artifact changed or exceeded its budget")
    return report


def bound_directory(root, relative):
    """Open a contained directory without traversing symlinks."""
    if (not isinstance(relative, str) or not relative or not relative.isprintable()
            or Path(relative).is_absolute() or Path(relative).as_posix() != relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("evidence path must be a contained relative file")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in Path(relative).parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def bound_names(root, relative, limit=4096):
    """Bound enumeration work; no directory symlink is followed."""
    descriptor = bound_directory(root, relative)
    try:
        names = []
        with os.scandir(descriptor) as entries:
            for index, entry in enumerate(entries):
                if index >= limit:
                    raise ValueError("board directory exceeds its entry budget")
                if entry.name.endswith(".json"):
                    names.append(entry.name)
        return sorted(names)
    finally:
        os.close(descriptor)


def bound_read(root, relative, limit=MAX_EVIDENCE_BYTES):
    """Bounded read through pinned directories; symlinks are never evidence."""
    if (not isinstance(relative, str) or not relative or not relative.isprintable()
            or Path(relative).is_absolute() or Path(relative).as_posix() != relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("evidence path must be a contained relative file")
    parts = relative.split("/")
    if len(parts) == 1:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    else:
        descriptor = bound_directory(root, "/".join(parts[:-1]))
    try:
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor)
        with os.fdopen(child, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("evidence is not a bounded regular file")
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if (len(content) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("evidence changed or exceeded its read budget")
            return content
    finally:
        os.close(descriptor)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def decision(root, relative, expected_digest, *, scope, phase, sha=None, scope_digest=None, artifact_digest=None):
    """Validate approval provenance structurally, never authenticate its author."""
    content = bound_read(root, relative)
    if not SHA256.fullmatch(expected_digest or "") or digest(content) != expected_digest:
        raise ValueError("decision digest mismatch")
    record = strict_json(content)
    if (not isinstance(record, dict) or record.get("decision") != "approve"
            or not valid_scope(scope) or not valid_scope(record.get("scope"))
            or record.get("scope") != scope or record.get("phase") != phase
            or not isinstance(record.get("approved_by"), str) or not record["approved_by"].strip()):
        raise ValueError("missing, contradictory or out-of-scope approval")
    timestamp = datetime.fromisoformat(record.get("approved_at", ""))
    if timestamp.tzinfo is None:
        raise ValueError("approval needs a timezone-aware decision time")
    has_subject = "subject_sha" in record
    has_scope = "scope_sha256" in record
    if (not (has_subject or has_scope)
            or (has_subject and (not SHA1.fullmatch(sha or "") or record["subject_sha"] != sha))
            or (has_scope and (not SHA256.fullmatch(scope_digest or "")
                              or record["scope_sha256"] != scope_digest))):
        raise ValueError("approval subject or scope is stale")
    if artifact_digest is not None and record.get("artifact_sha256") != artifact_digest:
        raise ValueError("approval does not bind the overridden artifact")
    source = record.get("source")
    if (not isinstance(source, dict) or source.get("kind") not in ("user-conversation", "approval-surface")
            or not isinstance(source.get("ref"), str) or not source["ref"].strip()
            or not SHA256.fullmatch(source.get("sha256", ""))):
        raise ValueError("approval needs a digest-bound trusted-source reference")
    source_content = bound_read(root, source.get("artifact"))
    if not source_content.strip() or digest(source_content) != source["sha256"]:
        raise ValueError("approval source is empty or changed")
    return record


def validate_bound(report, root, sha, phase, required, *, scope, scope_digest):
    """Strict policy for new protected transitions; historical reads stay valid."""
    if not isinstance(required, list) or not 1 <= len(required) <= MAX_REQUIRED_CHECKS:
        return ["required-check count exceeds the protected gate budget"]
    errors = validate(report, root, sha, phase, required, check_artifacts=False)
    if errors:
        return errors
    if not all(isinstance(report.get(key), str) and report[key].strip()
               for key in ("author", "reviewer")):
        return ["independent author and reviewer identities must be nonempty strings"]
    review_checks = [name for name in required
                     if name == "review" or report["checks"][name].get("kind") == "review"]
    if not review_checks:
        return ["a required passing independent review check is necessary"]
    measured = 0
    for name in required:
        check = report["checks"][name]
        try:
            if check.get("status") == "not_applicable":
                if name in review_checks:
                    raise ValueError("independent review cannot be excluded")
                if check.get("original_verdict") not in (None, "not_applicable"):
                    raise ValueError("failed evidence is not an applicability exception")
                approval = decision(root, check.get("decision_ref"), check.get("decision_sha256"),
                                    scope=scope, phase=f"exception:{name}", sha=sha, scope_digest=scope_digest)
                if approval["approved_by"] != check["approved_by"]:
                    raise ValueError("exception approver contradicts its source decision")
                continue
            if measured >= MAX_BOUND_ARTIFACT_BYTES:
                return ["protected gate artifact reads exceeded the aggregate byte budget"]
            content = bound_read(root, check.get("artifact"),
                                 limit=min(MAX_EVIDENCE_BYTES, MAX_BOUND_ARTIFACT_BYTES - measured))
            measured += len(content)
            if measured > MAX_BOUND_ARTIFACT_BYTES:
                return ["protected gate artifact reads exceeded the aggregate byte budget"]
            if not SHA256.fullmatch(check.get("artifact_sha256", "")) \
                    or digest(content) != check["artifact_sha256"]:
                raise ValueError("artifact digest mismatch")
            receipt = structured_artifact(content, check["artifact"])
            if isinstance(receipt, dict):
                for key in ("subject_sha", "git_sha"):
                    if key in receipt and receipt[key] != sha:
                        raise ValueError("receipt subject is stale or unknown")
                if "verdict" in receipt and receipt["verdict"] != "pass":
                    raise ValueError("receipt verdict is not pass")
                if "status" in receipt and receipt["status"] != "pass":
                    raise ValueError("receipt status is unsuccessful")
                if "self_sha256" in receipt:
                    body = {key: value for key, value in receipt.items() if key != "self_sha256"}
                    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                    if digest(encoded) != receipt["self_sha256"]:
                        raise ValueError("receipt self-hash mismatch")
                overrides = receipt.get("overrides", [])
                if not isinstance(overrides, list):
                    raise TypeError("invalid override history")
                if any(not isinstance(item, dict) or not all(
                    isinstance(item.get(key), str) and item[key].strip()
                    for key in ("who", "when", "reason")
                ) for item in overrides):
                    raise ValueError("incomplete override history")
                if any(isinstance(item, dict) and item.get("from_verdict") not in (None, "pass")
                       for item in overrides):
                    if check.get("disposition") != "approved_override":
                        raise ValueError("overridden failure needs an explicit disposition")
                    decision(root, check.get("override_decision_ref"), check.get("override_decision_sha256"),
                             scope=scope, phase=f"override:{name}", sha=sha, scope_digest=scope_digest,
                             artifact_digest=digest(content))
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            errors.append(f"{name}: invalid, stale or tampered bound evidence")
    return errors


def configured_required(config_path, phase):
    """Resolve the required check names; fail closed on any unusable config."""
    if config_path is None:
        return list(DEFAULT_REQUIRED[phase])
    try:
        data = json.loads(Path(config_path).read_text())
    except (OSError, ValueError):
        raise ValueError(f"config unreadable or not JSON: {Path(config_path).name}")
    return required_from_data(data, phase)


def required_from_data(data, phase):
    """The existing public configuration uses one unique list, not a phase map."""
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


def validate(report, root, sha, phase="complete", required=None, *, check_artifacts=True):
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
        if check_artifacts:
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
