# 0018 — Eleven-skill palette and an eleven-role starting team

Status: accepted · 2026-10-11

## Context

The 2026-10-10 scope expansion made the pack a full end-to-end team:
eval-first work, a project-context home and codebase understanding became
first-class before the installer milestone froze projections.

## Drivers

- Freezing the palette before the installer avoids regenerating goldens
  and manifests.
- Eval-first, principles and crawl are user-facing capabilities, not
  reference material.

## Options

- Keep eight skills and fold the new capabilities into existing skills:
  overloaded entries and blurred ownership.
- Ship the capabilities as three more discoverable skills with their own budgets.

## Outcome

The palette is eleven skills — adding `sf-eval`, `sf-principles` and
`sf-crawl` — with an eleven-role starting team, because distinct
capabilities deserve distinct, budgeted homes.

## Consequences

- Explicit-only invocation applies to entry and admin skills; working skills
  stay implicitly invocable.
- Architecture content folds into the existing design module, not a twelfth skill.
- Supersedes 0003's eight-skill palette.

## Confirmation

- `scripts/validate.py` names the eleven skills and eleven agents as data
  constants and validates the layout.
