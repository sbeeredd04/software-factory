# Coverage, bounds and degradation

What `scripts/crawl.py` sees, what it never claims, and how it fails.

## Language treatment

- **Python — full treatment.** Parsed with the standard-library `ast`
  module. The crawl sees what the grammar sees: imports (absolute and
  relative, resolved against the repo's module namespace), top-level
  definitions, calls inside function and method bodies, `__main__` guards,
  `__main__.py` modules and `pyproject.toml` script entry points. It never
  executes or imports the code, so runtime wiring (decorators that
  register, `__getattr__`, import hooks, framework route tables) is out of
  reach and lands under *Not determined*, never inferred. Calls inside
  nested functions are attributed to the enclosing function.
- **JavaScript/TypeScript — documented best effort.** Line-based lexical
  patterns only: `import` / `export … from` / `require` specifiers and
  `export function|class|const|let|interface|type|enum` names, plus
  `package.json` `main` and `bin`. No type resolution, no JSX awareness,
  no re-export chains; dynamic `import()` and computed requires are
  missed. Every best-effort section says so.
- **Everything else — counted, not parsed.** Files are counted by
  extension so the census shows where they live; no structure is claimed.

## Bounds

In a Git worktree, read-only `git ls-files --cached --others --exclude-standard
-z -- .` selects tracked paths plus nonignored new files beneath the requested
root. Git's standard excludes include `.gitignore`, `.git/info/exclude` and
configured global excludes; tracked ignored paths remain selected. Names are
NUL-delimited, deduplicated and sorted before parsing. This works with nested
roots and linked worktrees. Host folders have no blanket exclusion: tracked or
nonignored user code in `.agents` or `.codex` remains eligible. Git is invoked
with optional locks and filesystem monitoring disabled, never through a shell.

Git submodules are inventory boundaries, not recursively crawled projects;
selected directory boundaries and missing/deleted tracked paths are reported.
Run a separate crawl inside a submodule when its code is needed. An unusable
Git inventory (non-repository, unavailable executable, failure, ten-second
timeout or malformed paths) selects the filesystem fallback and records that
ignored files may then be included. Git stderr and exception text are omitted.
The report's `source.selection` and artifact header identify the actual policy;
fallback is never represented as a successful empty Git inventory.

Ignored directories: `.git`, `.hg`, `.svn`, `.idea`, `.vscode`,
`.software-factory` (the factory's own state, not codebase content),
`.venv`, `venv`, `env`, `__pycache__`, `.tox`, `.nox`, `.mypy_cache`,
`.pytest_cache`, `.ruff_cache`, `node_modules`, `dist`, `build`, `.next`,
`.nuxt`, `target`, `vendor`. Symlinks are not followed. Files over 1 MiB
are counted, not parsed. At most `--max-files` source files are parsed
(default 5000), in sorted path order; hitting the cap is reported as a
stated limit with the totals, never as silent truncation. Artifact tables
are capped the same way, with the remainder counted and stated.
These static bounds also apply to tracked paths. Packaging entry points are
read only from selected, nonsymlinked root manifests within the same size bound;
an ignored untracked `pyproject.toml` or `package.json` contributes no entry
points. Source files beneath a symlinked ancestor are not followed. This is a
static observation, not a security boundary against concurrent tree changes.

## Degradation and exit codes

- A file that fails to parse: the run completes, the path is reported with
  its error class (never the source text), every other finding stands, and
  a warning goes to stderr. Exit 0.
- No parseable source at all: the artifact is still written, every section
  present, each stating the absence. Exit 0.
- A missing or unreadable root: one `crawl:` message on stderr, exit 2, no
  partial write. An artifact write failure is also exit 2 and leaves the
  previous artifact intact (the write is an atomic replace).

The JSON report (`--json`) is the machine-readable form of the same
findings and carries no clock fields, so two runs over an unchanged tree
are byte-identical. `sf-help`'s discovery consumes the artifact; nothing
else re-crawls.
