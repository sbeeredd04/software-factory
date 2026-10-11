# Fitness functions

A fitness function is an objective, runnable integrity check on an
architecture characteristic; the automated ones run in CI like tests. The pack
states the contract and the bar — it never installs or configures the tool.
The consumer's repository owns its tooling.

## The countable bars

| Bar | Number to hold | Python | TS/JS | Java | Ruby |
|---|---|---|---|---|---|
| Import cycles | 0 | import-linter `forbidden` | dependency-cruiser | ArchUnit cycle rules | packwerk `dependency` |
| Layer direction | 0 upward imports | import-linter `layers` | eslint-plugin-boundaries / Nx enforce-module-boundaries | ArchUnit slices | packwerk |
| Declared module independence | no mutual imports between declared-independent modules | import-linter `independence` | eslint-plugin-boundaries | ArchUnit | packwerk `privacy` |
| Hub-module fan-in | flag a module imported by more than the tree-share bar | the audit's import fan-out, at module scope | same | same | same |
| Instability direction | a stable module never imports an unstable one; I = Ce/(Ce+Ca) from the import graph | grimp | dependency-cruiser | jdeps / ArchUnit | packwerk |
| Hotspot | top decile of churn × complexity over roughly three months | `git log` + the audit scan | same | same | same |
| Temporal coupling | co-change at or above 30% within a 2–3 month window | `git log` | same | same | same |

## Rules

- A fitness function that cannot fail is not one. Every bar above can go red.
- A red fitness function is a finding, not a re-architecture mandate. Report it
  with its measurement and route the judgment through the design palette.
- Module depth reads like the audit's smells: a module's interface should be
  small relative to the implementation mass it hides. Shallow modules — a wide
  interface over little hidden behavior — are Middle Man at architecture scale.
- Every adopted architecture pattern wires at least one of these checks; the
  decision record names which (see [adr.md](adr.md)).
