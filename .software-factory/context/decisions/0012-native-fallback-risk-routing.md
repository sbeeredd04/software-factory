# 0012 — Native fallback; risk and complexity routing without model pins

Status: accepted · 2026-10-11

## Context

External coding agents are optional capabilities. The pack must work with
only native host tooling and `gh`.

## Drivers

- Model aliases and account offerings vary across users and time.
- An installed binary is not proof of suitability or authorization.

## Options

- Always invoke a second premium model process: fragile and presumptuous.
- Hardcode premium/cheap model tiers: stale the day it ships.
- Probe executable, version and task suitability; route by risk and
  complexity with the native worker as the mandatory fallback.

## Outcome

Agents declare capabilities and are probed without running their CLIs;
routing chooses by risk, complexity, permissions and rework, because
capability evidence outlives pricing assumptions.

## Consequences

- Roles inherit the active model; the effective model is recorded only if
  observable.
- An unavailable required capability becomes a blocker or a safe
  fallback, never weaker proof.

## Confirmation

- Routing and probe guidance lives in `sf-agents` (onboarding milestone);
  role prompts carry `model: inherit` checked by `scripts/validate.py`.
