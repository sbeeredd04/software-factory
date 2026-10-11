---
name: sf-smell-audit
description: "Audits a codebase against the 23 Fowler code smells and writes a scored report card. Use when the user asks to rate dirty code, score code smells, find bloat, or produce a design report card for a repository."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: design
  release: v0.1
---

# Code smell audit

Score structure. Do not refactor in the same pass unless the user asked for both. Behavior stays put.

Palette and the smell-to-move table: [../sf-design/SKILL.md](../sf-design/SKILL.md), [../sf-design/references/smell-technique-map.md](../sf-design/references/smell-technique-map.md).

## Measure before you score

First discover the selected worktree's production tree, current schema, and project conventions. Do not invent a second data shape, and do not silently resolve conflicting contract instructions while describing a smell.

Exclude tests, virtualenvs, snapshots, and generated code from production totals. Count them separately. A large test suite is evidence against "no tests," not a large-class smell in the product.

On Python, parse the AST. Record:

- File length, and the share of lines in files at or above 400, 800, and 1,500.
- Function span (end line minus start line, including nested helpers) at three bars: 10 (catalog), 80, 300 (debt).
- Parameter count excluding `self`, at 4 (catalog) and 7 and 10 (debt).
- String equality on a name, tool, status, or kind. That is a switch even when the language has no `switch`.
- Import fan-out per file, and how many files mention the same seam.

A function span double-counts if you sum it with the helpers inside it. Report file lines as the mass. Report function spans as the units to split.

## Health

5 absent, 4 local, 3 present and contained, 2 expensive, 1 owns the tree. The family score is the mean of its smells. The overall score is the unweighted mean of the stable 23. Say so. The second, deep-pass catalog never enters the mean.

Always publish two numbers for Long Method and Long Parameter List:

- Catalog prevalence: share of functions past ~10 lines, and past 4 parameters.
- Debt tail: functions past 300 lines, parameter lists past 10.

A tree can have a wide catalog smell and still be healthy if the tail is short. A few 2,000-line functions are a 1 even if most functions are short.

## How to read this codebase style

- Procedural modules: score Large Class on the file, and name the biggest real class separately so a config bag is not called a god object.
- One dispatcher full of branches is Switch Statements; copied branch sets are the expensive form.
- Parallel packages with the same filenames are duplicate structure, not Parallel Inheritance Hierarchies, unless adding one type forces a twin in a second tree — say which smell you used.
- Boundary models with fields and no behavior are DTOs; score Data Class only when domain behavior lives in clients that should sit on that type.
- Comments that narrate a long method count; comments that state an invariant do not.

## Second pass: the deep catalog

The smell map's second catalog (twelve rows, deep pass only) runs on a deep audit request, or when the first pass scored 1–2 on the change-preventer family. Report each finding as a count against the row's detection bar; it never enters the 5-to-1 health score.

## History pass (optional)

Measure change, not just shape, from git over roughly a 2–3 month window — `git log --since=<date> --name-only --format=%h` feeds the counts. Report as measured facts, never scores, each marked confirmed (with the command) or unconfirmed:

- Hotspots: the top decile of churn × complexity.
- Temporal coupling: pairs that co-change in at least 30% of their commits.
- A single-dominant-author note where one author wrote nearly all of a file.

These facts justify the first move for divergent change and shotgun surgery, and locate boundary defects that static shape misses.

## Architecture smells (module scope, on request)

Report as counts and ratios with the same confirmed/unconfirmed marking and no re-architecture recommendation: import cycles (0 allowed), layer-direction breaches, hub-module fan-in above the tree-share bar, a stable module importing an unstable one, and shallow modules (interface size versus hidden implementation mass).
Bars and per-ecosystem tools: [../sf-design/references/fitness-functions.md](../sf-design/references/fitness-functions.md).

## Report card

Lead with the overall health, the worst family, and the debt tail. Then:

1. Family means.
2. All 23 smells: health, one confirmed fact (file and size, or "no instances found").
3. Catalog prevalence beside the tail.
4. What is already clean, so the next pass does not "fix" it.
5. The first move for each smell scored 1 or 2, taken from the map. Name the move. Do not write the patch.

Mark each fact confirmed (path, count, or command) or unconfirmed. An unconfirmed cause is not a score.

## Project principles

Read the repository's own governing principles; they remain authoritative.
Do not create a second format.
