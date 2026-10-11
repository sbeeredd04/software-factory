---
name: sf-crawl
description: Understands a codebase read-only. Crawls the abstract syntax tree to build call trees, a module map and entry points, then writes CODEBASE.md into the project-context home so every worker starts from real context. Use when the factory needs to learn an unfamiliar or changed codebase.
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: crawl
  release: v0.1
---

# sf-crawl (placeholder)

> **Placeholder — this is not the shipped skill.** This file exists so the
> eleven-skill layout validates. The full crawl skill (a read-only AST crawl
> that builds call trees, a module map and entry points, then writes
> `CODEBASE.md`) is authored in the expansion milestone and will replace this
> body. Until then, do not rely on this skill for codebase understanding.

Intended scope, so readers know what is coming: `sf-crawl` reads code and
never changes it. Its only write is the crawl artifact
`.software-factory/context/CODEBASE.md` — the map every worker starts from
instead of rediscovering the codebase — refreshed as the tree changes.
