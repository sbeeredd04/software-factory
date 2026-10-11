# 0007 — Pinned official BMad install; no vendoring

Status: accepted · 2026-10-11

## Context

Planning uses BMad Method v6. The pack must never ship BMad's content,
yet installs must be reproducible.

## Drivers

- The official installer owns BMad rendering and customization.
- Unpinned upstreams drift; vendored bodies go stale and misattribute.

## Options

- Vendor BMad bodies into the pack: attribution and staleness problems.
- Install from mutable upstream `main`: unreproducible.
- Invoke `npx bmad-method@6.12.0 install` pinned, skip existing installs,
  and record resolved module versions.

## Outcome

Fresh setups run the pinned official installer with prerequisite checks
and stage/validate its output before applying, because reproducibility
without ownership theft requires the official path.

## Consequences

- Node >= 20.12, uv and Python >= 3.11 are checked; npm execution is
  disclosed.
- A missing prerequisite degrades the profile with clear instructions;
  plain Markdown planning remains an explicit reduced profile.

## Confirmation

- One network-marked end-to-end test installs BMad into a temporary
  directory (BMad milestone); all other tests mock the subprocess.
