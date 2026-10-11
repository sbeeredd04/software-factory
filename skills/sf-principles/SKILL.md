---
name: sf-principles
description: "Authors the project's core principles with the user and keeps the committed .software-factory/context/ home honest. Use when drafting or changing principles (product, conventions, risk, evals), judging work against them, or recording a decision."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: principles
  release: v0.1
---

# sf-principles

The core principles are the project's standing law: four user-authored
modules — `product.md`, `conventions.md`, `risk.md`, `evals.md` — under the
configured principles paths. Contracts: [modules](references/modules.md).

## Authoring flow

Interview (user answers plus the codebase map), draft, get explicit user
sign-off, then record; re-read before relying on them. The skill proposes
and records — it never silently applies an edit, never invents content.

## Enforcement

Read the principles before planning, before design scoring or judgment, and before
review — they are the design-review bar. A conflict with a recorded decision
escalates to the named human owner with a recommendation, never silently resolved;
a missing, empty or contradictory set blocks the work instead of being guessed.

## One home

Exactly one home, no competing copy anywhere: pre-existing principles
documents are discovered and pointed at, never duplicated; the installer
never writes a principles body. Layout, owners, decision-record contract:
[context-home](references/context-home.md).
