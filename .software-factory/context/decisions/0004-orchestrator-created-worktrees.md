# 0004 — Orchestrator-created exact worktrees, never automatic isolation

Status: accepted · 2026-10-11

## Context

Workers need isolated checkouts. Host-provided automatic worktrees can
select the wrong repository or base in multi-repo workspaces.

## Drivers

- Explicit ownership of the target worktree survives host changes.
- One writer per conflicting path across one Git common dir.

## Options

- Host automatic worktrees (`isolation: worktree`, CLI flags): convenient
  but host-controlled and wrong-repo prone.
- Code directly in the user's checkout: simple and unsafe.
- The orchestrator inspects the repo and creates the exact story worktree
  before dispatch, claiming its paths.

## Outcome

The orchestrator creates and claims the worktree; agents never use
automatic isolation, because explicit ownership is the only form that
survives host behavior changes.

## Consequences

- One integration owner serializes merges to the integration branch.
- Worktrees are not credential, port, database or network sandboxes.

## Confirmation

- `scripts/validate.py` refuses `isolation` in role agents; kernel claim
  tests cover parent/child collisions (`tests/test_state.py`).
