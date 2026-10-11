# 0006 — Multiple distribution profiles with honest completeness

Status: accepted · 2026-10-11

## Context

Users discover skills through marketplaces, `npx skills add`, and direct
install. Each surface installs a different subset of the factory.

## Drivers

- Skill discovery works across hosts; plugins suit teams.
- Project setup still needs config, authority, BMad and host trust.

## Options

- Marketplace only: discovery without the installer transaction.
- Installer only: full function with weak discovery.
- All three profiles, each documented for exactly what it installs.

## Outcome

Ship the full project installer, `npx skills add` compatibility and
marketplace bundles, and state plainly that they are not equivalent,
because honest completeness beats a pretend one-click story.

## Consequences

- Plugin commands are namespaced; plain invocation belongs to project
  installs.
- Plugin/project duplication is detected and requires migration, never
  silent removal.

## Confirmation

- Distribution manifests validate under `check-jsonschema` in the gate
  (distribution milestone); docs carry the capability matrix per profile.
