# 0003 — Eight discoverable skills with progressive disclosure

Status: superseded-by-0018

## Context

The loop could be exposed as many commands or as a small skill set; a
crowded command surface hides the one request interface.

## Drivers

- One request is the interface; phase detail must stay discoverable, and
  descriptions stay short so hosts can route well.

## Options

- Separate plan/dispatch/verify/integrate/checkpoint commands: explicit
  but noisy, and each command drifts.
- One giant prompt: no discoverability, no budgets.
- Eight skills with references for phases.

## Outcome

Ship `software-factory`, `sf-help`, `sf-agents`, `sf-evolve` and the four
design skills, with detail in linked references, because progressive
disclosure keeps the entry surface small without losing depth.

## Consequences

- The entry skill stays at or under 150 lines; descriptions under 300 characters.
- Status, checkpoint and resume remain inferred intents, not new skills.

## Confirmation

- `scripts/validate.py` enforces palette, entry length and description budgets.

## Superseded

The 2026-10-10 scope expansion added `sf-eval`, `sf-principles` and
`sf-crawl`; see 0018 for the eleven-skill palette.
