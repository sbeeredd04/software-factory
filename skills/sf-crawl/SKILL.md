---
name: sf-crawl
description: "Maps a codebase read-only into CODEBASE.md: module map, call edges and entry points from the Python AST, documented best effort for other languages. Use when the factory needs to learn or refresh its picture of a codebase."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: crawl
  release: v0.1
---

# sf-crawl

Understand a codebase once, then work from the map. This skill regenerates
`.software-factory/context/CODEBASE.md`, the codebase map every worker reads
before planning or implementing.

## Read-only rules

The crawl is strictly read-only: it never installs tooling or dependencies,
never executes project code (it parses, never imports), never runs a model
or an agent CLI, and never fetches from the network. Its only write inside
the crawled repository is the single artifact; what it cannot parse it
reports, never guesses.

## Run it

From the consumer repository root (`<skill-dir>` is the installed skill
directory, e.g. `.claude/skills/sf-crawl`, `.agents/skills/sf-crawl`):

    python3 <skill-dir>/scripts/crawl.py .

The deterministic script builds the map — do not read files yourself. One
command regenerates the artifact atomically in place; re-run whenever the
tree changes. Output is deterministic: a refresh changes only what the tree
change changed, with no cache and no partial state. `--json <path>` adds
the machine-readable report; `--help` lists the options.

## Coverage

- **Full treatment — Python:** `ast`-parsed module map, import edges, call
  edges and entry points.
- **Documented best effort — JavaScript/TypeScript; everything else is
  counted, not parsed.** Unknown is reported as unknown. Detail:
  [coverage and bounds](references/coverage.md).

## The artifact

`CODEBASE.md` carries the module map, entry points, measured dependency
direction and per-module facts marked confirmed or unconfirmed, under its
own stated limits — contract: [artifact reference](references/artifact.md).
`sf-help` discovery consumes this artifact and never re-crawls; this is the
factory's one crawler.
