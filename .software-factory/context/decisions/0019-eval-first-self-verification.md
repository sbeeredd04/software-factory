# 0019 — Eval-first, with the pack verifying itself

Status: accepted · 2026-10-11

## Context

The expansion made evals a precondition of work: stories carry
fail_to_pass and pass_to_pass cases, and no story is done without green
cases or a recorded override.

## Drivers

- A method that grades consumer work must grade its own work the same
  way; anything less is unproven guidance.
- Deterministic grading keeps the gate cheap, offline and trustworthy.

## Options

- Ship eval guidance but exempt the pack itself: the method's core claim
  would rest on nothing.
- Dogfood: a committed plan for the pack, run by one command inside the
  gate.

## Outcome

The pack's own eval plan lives in `evals/`, carries its own sign-off, and
runs in `premerge` mode inside `scripts/check_all.sh`, because the suite
that proves the skills work is the suite that runs on every change.

## Consequences

- The pack's cases are fully deterministic and offline; no judge cases.
- A red verdict fails the gate, so eval debt blocks merges like any other
  red check.

## Confirmation

- `tests/test_dogfood.py` runs the suite offline with agent-CLI guard
  stubs; receipts verify through `sf_eval.py verify`.
