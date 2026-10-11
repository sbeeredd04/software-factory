# 0002 — One canonical source, generated host projections

Status: accepted · 2026-10-11

## Context

The pack serves Claude Code, Cursor and Codex, whose skill and agent
formats differ. Hand-maintaining three trees would fork behavior.

## Drivers

- Host differences are adapter data, not independent workflows.
- The canonical tree must stay usable through `npx skills add`.

## Options

- Separate host repositories: maximal fit, tripled maintenance and drift.
- Rich host-specific frontmatter everywhere, relying on other hosts to
  ignore it: pollutes the canonical source.
- One canonical source with generated projections carrying provenance and
  content hashes.

## Outcome

Skills and role prompts are hand-edited once in `skills/` and `agents/`;
host metadata lives in `hosts/`; the installer projects each host's files,
because a single source is the only way three hosts stay behaviorally
identical.

## Consequences

- Canonical and projected formats are validated separately.
- Codex role conversion omits `model` to inherit rather than copying it.
- Generated files are never hand-edited; fixes land in the source.

## Confirmation

- `scripts/validate.py` enforces canonical frontmatter and layout; golden
  projection tests arrive with the installer milestone.
