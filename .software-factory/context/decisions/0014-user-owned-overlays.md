# 0014 — User-owned overlays and BMad custom TOML, never patched bodies

Status: accepted · 2026-10-11

## Context

The factory improves by folding in third-party skills and lessons.
Editing installed bodies destroys updateability and trust.

## Drivers

- A learned lesson is evidence, not authority to weaken a gate.
- Updates must not silently discard user adaptation.

## Options

- Edit rendered BMad or pack files in place: lost on the next install.
- Append every discovered skill to the orchestrator: prompt rot.
- Register source-pinned skills; extend BMad through custom TOML; bind
  overlays to base hashes so they survive reinstall.

## Outcome

Evolution flows through a registry, hash-bound overlays and a retro to
proposed-patch to independent-review to tested-apply pipeline, because
adaptation must be owned, reviewable and reversible.

## Consequences

- Upstream drift requires an explicit overlay rebase with canary tests.
- Policy, trust or permission changes always require a human decision.

## Confirmation

- The evolve pipeline is specified in `sf-evolve` (onboarding milestone);
  the no-self-modification rule is a stated hard boundary.
