# 0017 — Clean-room public release scan without publishing the denylist

Status: accepted · 2026-10-11

## Context

The pack was generalized from a private factory. The release must contain
no private terms, yet committing those terms as a test list would disclose
them.

## Drivers

- The denylist would itself be a leak.
- Generalization replaces assumptions and mechanics, not just strings.

## Options

- Commit every known private name as a plain denylist: self-defeating.
- Trust regexes alone: misses project-specific terms.
- Hash private terms into a SHA-256 denylist plus generic patterns for
  paths, secrets and hosted domains; independent editorial review covers
  prose and history.

## Outcome

`scripts/scan_public.py` scans tracked files, generated output and history
against hashed terms and generic shapes, failing closed on any hit,
because verifiable cleanliness needs a checkable artifact that is not
itself sensitive.

## Consequences

- A missing scan input is unverified or blocked, never a pass.
- Public examples use invented generic domains and identities.

## Confirmation

- `scripts/scan_public.py` runs in the gate and on the full history before
  publication; `tests/test_tools.py` covers hit and clean cases.
