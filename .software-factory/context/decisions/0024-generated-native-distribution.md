# 0024 — Generated native marketplace release artifacts

Status: accepted · 2026-10-15

## Context and decision source

Canonical skills omit host-only controls. Native policies are generated,
and repository rules forbid committing generated projections. Older
acceptance language expected native marketplace paths in the source checkout.
The owner approved generated native bundles in the active implementation
conversation, then confirmed both recommended decisions.

## Outcome

Keep portable canonical skills discovery in the source repository and build
self-contained native plugin/marketplace roots as release artifacts.
Every local component and catalog reference resolves inside the artifact
being offered. The full project installer remains the project setup route.

## Boundaries

- Generated dist output stays untracked and is never hand-edited.
- Native bundles use the approved host projections from canonical sources.
- Portable skills discovery is labeled skills-only; it does not establish
  full setup, invocation policy, roles, hooks or host trust.
- Deterministic local generation and static schema checks do not prove
  live host loading, marketplace acceptance or publication.
- Final publication and external effects require their own scoped decision.

## Confirmation

Story 24 proves reproducible external generation, reference containment,
bootstrap integrity and canonical discovery before release claims.
