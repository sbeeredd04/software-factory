# 0015 — Alarm-first resource policy with optional explicit hard limits

Status: accepted · 2026-10-11

## Context

Legitimate work may span sessions and its cost varies. Arbitrary clocks
kill good work; no monitoring invites runaway spend.

## Drivers

- Stall detection and permission boundaries beat task clocks.
- A forced stop must preserve the next action, not discard work.

## Options

- Fixed global turn, time or cost limits: blunt and wrong-sized.
- No resource monitoring at all: irresponsible.
- Warn by default; an explicitly opted-in hard cap causes a durable pause
  with preserved state.

## Outcome

Cost and stall thresholds alarm by default and hard caps are opt-in,
because guidance scales across users while coercion must be chosen.

## Consequences

- Unknown cost is reported as unknown; model-call caps can overshoot and
  are not billing ceilings.
- Repeated equivalent calls to evade an alarm violate the policy, as does
  claiming completion after a forced stop.

## Confirmation

- Budget keys are documented in the configuration reference; the
  checkpoint preserves the resume state (`tests/test_state.py`).
