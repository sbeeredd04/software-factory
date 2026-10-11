# 0016 — Offline, static validation by default; no forbidden CLI dependency

Status: accepted · 2026-10-11

## Context

The pack's own CI must be deterministic, credential-free and safe for
forks. Live host CLIs are unavailable or prohibited in validation.

## Drivers

- Static tests can prove formats and mechanics, not host execution.
- Paid or vendor-locked smoke runs exclude contributors.

## Options

- Vendor CLI validation in required CI: prohibited and brittle.
- Paid headless workers as smoke proof: exclusionary and flaky.
- Python unittest, schema and format validators, installer fixtures,
  offline eval grading; live smoke only as an explicit, optional extra.

## Outcome

All required validation runs offline with no model or agent CLI, and host
compatibility claims are version-qualified and honest about what was not
executed, because a gate everyone can run beats a gate that hides.

## Consequences

- CI covers macOS and Linux across Python 3.11 to 3.13.
- Unverified live behavior is stated in the limitations docs, never
  implied.

## Confirmation

- `scripts/check_all.sh` runs the offline gate; `tests/` use PATH guard
  stubs proving no agent CLI is ever invoked.
