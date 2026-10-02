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

Exclude tests, virtualenvs, snapshots, and generated code from production totals. Count them separately. A large test suite is evidence against "no tests," not a large-class smell in the product.

On Python, parse the AST. Record:

- File length, and the share of lines in files at or above 400, 800, and 1,500.
- Function span (end line minus start line, including nested helpers) at three bars: 10 (catalog), 80, 300 (debt).
- Parameter count excluding `self`, at 4 (catalog) and 7 and 10 (debt).
- String equality on a name, tool, status, or kind. That is a switch even when the language has no `switch`.
- Import fan-out per file, and how many files mention the same seam.

A function span double-counts if you sum it with the helpers inside it. Report file lines as the mass. Report function spans as the units to split.

## Health

5 absent, 4 local, 3 present and contained, 2 expensive, 1 owns the tree. The family score is the mean of its smells. The overall score is the unweighted mean of all 23. Say so.

Always publish two numbers for Long Method and Long Parameter List:

- Catalog prevalence: share of functions past ~10 lines, and past 4 parameters.
- Debt tail: functions past 300 lines, parameter lists past 10.

A tree can have a wide catalog smell and still be healthy if the tail is short. A few 2,000-line functions are a 1 even if most functions are short.

## How to read this codebase style

- Procedural modules: score Large Class on the file. Name the biggest real class separately so a config bag is not called a god object.
- One dispatcher full of branches is Switch Statements. Copied branch sets are the expensive form.
- Parallel packages with the same filenames are not Parallel Inheritance Hierarchies unless adding one type forces a twin in a second tree. Score the package echo as duplicate structure, and say which smell you used.
- Boundary models with fields and no behavior are DTOs. Score Data Class only when domain behavior lives in clients that should sit on that type.
- Comments that narrate a long method count. Comments that state an invariant do not.

## Report card

Lead with the overall health, the worst family, and the debt tail. Then:

1. Family means.
2. All 23 smells: health, one confirmed fact (file and size, or "no instances found").
3. Catalog prevalence beside the tail.
4. What is already clean, so the next pass does not "fix" it.
5. The first move for each smell scored 1 or 2, taken from the map. Name the move. Do not write the patch.

Mark each fact confirmed (path, count, or command) or unconfirmed. An unconfirmed cause is not a score.

## Project principles

Read the repository's own governing principles; they remain authoritative. Discover the selected worktree's production tree, current schema, and project conventions before scoring. Do not invent a second data shape, and do not silently resolve conflicting contract instructions while describing a smell.
