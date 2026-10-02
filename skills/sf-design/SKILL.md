---
name: sf-design
description: "Routes software design work to the sf-smell-audit, sf-refactor and sf-patterns skills. Use when the user asks about dirty code, clean code, code smells, refactoring, technical debt, design patterns or a design report card, or names Refactoring.Guru, Fowler or the Gang of Four."
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

Load one. Do not load all three unless the user asked for a full report card. A report card uses audit first, then one technique per failing smell, then a pattern check that mostly says "do not add this."

## What this palette is for

Refactoring changes structure and keeps behavior. A smell is a sign, not a verdict that a pattern must be installed. Technical debt is Ward Cunningham's loan: speed borrowed now, paid as slower change later. The interest on this kind of debt is shotgun edits and divergent modules, not a missing diagram.

## Rules that outrank the catalog

- A smaller diff that hides the symptom fails. Fix the class of problem in the module that already owns it.
- No second path, no flag whose only job is to hide a smell, no helper with one caller "for now."
- Separate a refactor from a feature. Tests stay green after each move.
- In a procedural codebase, "class" means the module. Extract a module before inventing a hierarchy.
- A pattern is the end of a refactor when duplication or a repeated switch is already there. It is speculative generality when it arrives first.
- Strategy, Command, and Factory are often a function in Python. A class per case is the criticism page's hammer.

## Sources

Read [references/sources.md](references/sources.md) when you need the book or the page. Read [references/smell-technique-map.md](references/smell-technique-map.md) when a smell already has a score.

## Project principles

Read the repository's own governing principles; they remain authoritative. Discover the project's conventions — its architecture, contracts, and shared logging and observability paths — in the selected worktree. Do not create a second format.
