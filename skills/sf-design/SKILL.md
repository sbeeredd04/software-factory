---
name: sf-design
description: "Routes design work to sf-smell-audit, sf-refactor, sf-patterns and the architecture references. Use for dirty code, code smells, refactoring, technical debt, design patterns, a design report card, or architecture calls: service split, CQRS, event-driven, hexagonal, decision records."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: design
  release: v0.1
---

# Software design palette

Original playbook. Names and URLs point at [Refactoring.Guru](https://refactoring.guru/refactoring), Fowler's *Refactoring*, and the Gang of Four. Do not paste their prose into a review or a skill.

## Which skill

| Job | Skill |
|---|---|
| Audit a tree against the smell catalog | `sf-smell-audit` |
| Choose a refactoring technique and a safe order of moves | `sf-refactor` |
| Judge whether a pattern belongs | `sf-patterns` |
| Architecture judgment: boundaries, the dependency rule, "should this be a service", CQRS, event-driven, hexagonal, decision records | [architecture-patterns](references/architecture-patterns.md), [fitness-functions](references/fitness-functions.md), [adr](references/adr.md), [modern-patterns](references/modern-patterns.md) |

Load one. Do not load all three unless the user asked for a full report card. A report card uses audit first, then one technique per failing smell, then a pattern check that mostly says "do not add this," then the architecture check.

Before scoring or judging, discover the project's conventions — its architecture, contracts, and shared logging and observability paths — in the selected worktree.

## What this palette is for

Refactoring changes structure and keeps behavior. A smell is a sign, not a verdict that a pattern must be installed. Technical debt is Ward Cunningham's loan: speed borrowed now, paid as slower change later. The interest on this kind of debt is shotgun edits and divergent modules, not a missing diagram.

## Rules that outrank the catalog

- A smaller diff that hides the symptom fails. Fix the class of problem in the module that already owns it.
- No second path, no flag whose only job is to hide a smell, no helper with one caller "for now."
- Separate a refactor from a feature. Tests stay green after each move.
- In a procedural codebase, "class" means the module. Extract a module before inventing a hierarchy.
- A pattern is the end of a refactor when duplication or a repeated switch is already there. It is speculative generality when it arrives first.
- Strategy, Command, and Factory are often a function in Python. A class per case is the criticism page's hammer.
- A second deployable, a second data model, or a second publish path is an architecture decision: it needs a decision record and a wired check, not just a diff.
- If a principle forbids or mandates a pattern, the principle wins with no re-derivation: record the application of the principle, not a fresh decision. A recorded decision that conflicts with the principles stops and surfaces to the human owner named in the project's risk module, never silently resolved; the resolution is a superseding decision record, and a change to the law itself is a proposed principles edit.

## Sources

Read [references/sources.md](references/sources.md) when you need the book or the page. Read [references/smell-technique-map.md](references/smell-technique-map.md) when a smell already has a score.

## Project principles

Read the repository's own governing principles; they remain authoritative.
Do not create a second format.
