# CODEBASE.md — artifact contract

`.software-factory/context/CODEBASE.md` is generated content: produced by one
documented command, never hand-edited, rewritten atomically in place — no
second copy, no backup file. It is committed so every worker starts from the
same map.

    python3 <skill-dir>/scripts/crawl.py .

Run from the repository root. Refresh is a re-run of that command: output is
deterministic, so over an unchanged tree only the revision and timestamp
header lines may differ, and a real tree change updates only the sections it
touches. A failed run leaves the previous artifact intact.

## Header

The header states the tool and the exact regeneration command, the source
revision (the repository's `HEAD`, or `unknown (not a git repository)`) and
the UTC generation timestamp.
It also identifies `git-tracked-and-unignored` or `filesystem-fallback` file
selection. The machine report records this as `source.selection`; exclusions,
fallback limitations, missing tracked paths and submodule boundaries follow the
[coverage contract](coverage.md). The census and packaging entry points use that
same selected inventory, before source parsing and table caps.

## Sections

- **Module map** — every parsed Python module: dotted name, file, definition
  count, internal-import count and import fan-out (distinct import targets).
- **Import edges** — the measured internal dependency direction, each edge
  confirmed with the importing file. Cycles are reported as measured, never
  judged.
- **Call tree, rendered as call edges** — per function, the names it calls.
  A name resolvable to a same-module definition or an internal from-import
  is marked `confirmed: <target>`; every other name is listed as
  unconfirmed, never resolved by guessing.
- **Entry points** — evidence only, each confirmed with its source: a
  `__main__` guard or a `__main__.py` module (path), `pyproject.toml`
  `[project.scripts]` / `[project.gui-scripts]`, or `package.json`
  `main` / `bin` (best effort). No evidence, no entry point.
- **Best effort** — JavaScript/TypeScript per [coverage](coverage.md).
- **Files not parsed** — every parse failure with its error class and line,
  never the source text.
- **Not determined** — what the crawl could not establish, stated plainly.
- **File census** — counts by extension, so unseen file classes are visible.

Every fact in the artifact is marked confirmed (a path, a count or a command
is cited) or unconfirmed. An inferred finding presented as measured is a
defect; treat it as a crawl bug, not as context.
