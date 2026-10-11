# 0011 — Evidence binds to actual subjects; applicability is configurable

Status: accepted · 2026-10-11

## Context

Local tests, combined integration and deployed effects prove different
things. Reused or unbound receipts make green gates meaningless.

## Drivers

- Pull-request head, merge candidate, integration and serving commits are
  distinct subjects.
- A fixed five-check gate makes docs-only work needlessly brittle.

## Options

- Accept worker summaries as proof: unfalsifiable.
- One fixed gate for every change: rigid and gameable.
- Receipts bind to subject, diff, config and artifact hashes; required
  checks are configurable, with explicit approved waivers.

## Outcome

The evidence gate binds every receipt to a full subject SHA and treats
missing, unknown, skipped or infra-error results as failures, because
only subject-bound evidence survives rebases and retries.

## Consequences

- The structural gate cannot attest artifact truth or security-grade
  independence; independent review and protected CI are still needed.
- `not_applicable` requires an approval record, never a bare skip.

## Confirmation

- `tests/test_gate.py` covers SHA matching, author/reviewer separation,
  phase checks and the waiver path.
