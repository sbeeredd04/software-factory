# Shared repository fixtures

Deterministic fixture repositories for the codebase-understanding features.
They are the single fixture set for the one crawler: `skills/sf-crawl/scripts/crawl.py`
is tested against them today, and `sf-help`'s discovery consumes the same set
(sf-help never re-crawls; it reads the crawl artifact). Do not add a second
fixture set for codebase discovery.

- `python-cli/` — a small Python package: full AST treatment (module map,
  import edges, call edges, entry points).
- `typescript-web/` — a small TypeScript app: documented best-effort lexical
  treatment.
- `greenfield/` — a repository with no parseable source: the empty-artifact
  case, every section present and stating the absence.

Fixture rules: the crawler must leave these trees byte-identical (tests hash
them before and after), every Python file must compile and lint clean, and no
fixture may contain private terms, secrets or absolute user paths.
