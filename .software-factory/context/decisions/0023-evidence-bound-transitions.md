# 0023 — Evidence-bound acceptance transitions

Status: accepted · 2026-10-15

## Context and decision source

The repository owner was asked whether new built/done transitions should
require SHA-bound passing evidence, independent review and source-linked
required checkpoints. After an initial guidance-only answer, the owner
explicitly revised it: "actually you can run recommended for both."
This later instruction in the active implementation conversation governs.

## Outcome

Implement the reviewed transition proposal in the full SDLC delivery plan.
New built/done transitions consume the applicable subject-bound gate,
independent review and required owner checkpoint records. Failed or missing
proof leaves the authoritative record unchanged. Preserve historical records,
the existing status vocabulary and review-counts-as-met readiness semantics.

## Boundaries

- A local actor label or structurally valid source reference does not
  authenticate a human or establish the truth of an external effect.
- Evidence integrity, current subject identity and actual effect observation
  remain distinct responsibilities.
- Required epic acceptance and publication decisions are still separate.
- Principal-engineer implementation, independent review and demonstrated
  rejection/recovery cases precede claims that enforcement works.

## Confirmation

Story 44 owns implementation and proof. This approval authorizes that work;
it does not record a successful gate, integration, deployment or acceptance.
