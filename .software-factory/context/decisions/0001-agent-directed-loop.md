# 0001 — Agent-directed loop with a small evidence kernel

Status: accepted · 2026-10-11

## Context

The pack must add delivery and recovery capability without becoming a
platform; only local invariants need deterministic protection.

## Drivers

- No new scheduler, daemon, status or memory service to operate; concurrent
  writes and stale evidence are the real failure modes.

## Options

- A deterministic DAG/workflow service: strong ordering, but a second
  system to install, run and trust.
- A prompt-only process with no durable state: zero footprint, but claims,
  checkpoints and evidence gates become unenforceable.
- Agent-directed loop with a small stdlib kernel for claims, checkpoints
  and gates.

## Outcome

The main session owns planning, staffing, acceptance and communication;
Python helpers own only local claims, checkpoints, validation and recovery
pointers, because that is the smallest layer that protects concurrency and
evidence without taking over judgment.

## Consequences

- Recovery requires explicit reconciliation; helpers cannot guarantee
  external exactly-once effects or cross-machine locking.
- The pack never claims an unbypassable merge gate.

## Confirmation

- `tests/test_state.py`, `tests/test_gate.py`, `tests/test_hook.py` prove
  the kernel contracts; `scripts/validate.py` keeps the layout canonical.
