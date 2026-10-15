#!/usr/bin/env python3
"""sf-crawl: the factory's one deterministic, read-only codebase crawler.

Walks a repository without modifying it and produces:

- ``CODEBASE.md`` (default ``<root>/.software-factory/context/CODEBASE.md``):
  the regenerable, committed codebase map with its stated limits, rewritten
  atomically in place (no second copy, no backup file).
- an optional JSON report (``--json PATH``, ``-`` for stdout): the
  machine-readable crawl findings. It carries no clock fields, so two runs
  over an unchanged tree produce byte-identical JSON.

Treatment: Python receives the full treatment (standard-library ``ast``):
module map, import edges, extracted call edges and entry points.
JavaScript/TypeScript receive documented best-effort lexical analysis
(import specifiers and exported names only). Everything else is counted by
extension.

Read-only rules: no installs, no execution of project code (AST parse,
never import), no model or agent CLI, no network. The only write inside the
crawled repository is the single artifact; ``--json`` and ``--artifact``
write exactly where the caller points.

Exit codes: 0 on success (warnings on stderr included), 2 on a usage or
environment error (one ``crawl:`` message on stderr, no partial write).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "sf-crawl/1"
TOOL_PATH = "skills/sf-crawl/scripts/crawl.py"
DEFAULT_ARTIFACT = ".software-factory/context/CODEBASE.md"
DEFAULT_MAX_FILES = 5000
MAX_FILE_BYTES = 1_000_000
MAX_MODULE_ROWS = 100
MAX_CALL_ROWS = 100
MAX_CALLS_PER_FUNCTION = 25
MAX_BEST_EFFORT_ROWS = 50
MAX_CENSUS_ROWS = 15

IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".software-factory",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "vendor",
    }
)
PY_SUFFIXES = frozenset({".py", ".pyi"})
TS_SUFFIXES = frozenset({".ts", ".tsx"})
JS_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs"})
SOURCE_SUFFIXES = PY_SUFFIXES | TS_SUFFIXES | JS_SUFFIXES

IMPORT_RE = re.compile(
    r"""^[^\S\n]*(?:import\s[^'"\n]*?\sfrom|import|export\s[^'"\n]*?\sfrom)"""
    r"""\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)"""
)
EXPORT_RE = re.compile(
    r"^[^\S\n]*export\s+(?:async\s+)?(?:default\s+)?"
    r"(?:function|class|const|let|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
)
MAIN_GUARD_OPS = (ast.Eq,)


def eprint(message: str) -> None:
    print(f"crawl: {message}", file=sys.stderr)


def source_revision(root: Path) -> str | None:
    """Best-effort read-only `git rev-parse HEAD`; None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
             "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def inventory(root: Path) -> tuple[list[str], str, list[str]]:
    """Select Git paths, or explicitly fall back to the static filesystem walk.

    Git's NUL-delimited bytes retain spaces and newlines without shell parsing.
    Cached paths include tracked ignored files; other paths obey Git's excludes.
    No hooks, project programs, submodules or filesystem monitor are invoked.
    """
    problems: list[str] = []
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
             "-C", str(root), "ls-files", "--cached", "--others",
             "--exclude-standard", "-z", "--", "."],
            capture_output=True, timeout=10, check=False,
        )
        if result.returncode == 0:
            raw = result.stdout
            if raw and not raw.endswith(b"\0"):
                raise ValueError("unterminated inventory")
            paths: set[str] = set()
            for item in raw.split(b"\0")[:-1]:
                rel = item.decode("utf-8")
                # Untracked nested repositories are returned with a trailing /.
                rel = rel.removesuffix("/")
                if (not rel or rel.startswith("/")
                        or any(part in {"", ".", ".."} for part in rel.split("/"))):
                    raise ValueError("unsafe inventory path")
                paths.add(rel)
            return sorted(paths), "git-tracked-and-unignored", problems
        reason = "Git inventory unavailable (non-repository or Git failure)"
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        # Never copy Git stderr, exception text or absolute paths to artifacts.
        reason = f"Git inventory unavailable ({type(exc).__name__})"
    problems.append(
        reason + "; filesystem fallback includes ignored files under static bounds"
    )
    paths = []

    def onerror(error: OSError) -> None:
        try:
            rel = Path(error.filename).relative_to(root).as_posix()
        except (TypeError, ValueError):
            rel = "(unknown directory)"
        problems.append(f"could not read: {rel} (counted only)")

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in IGNORE_DIRS and not (Path(dirpath) / name).is_symlink()
        )
        paths.extend((Path(dirpath) / name).relative_to(root).as_posix()
                     for name in sorted(filenames))
    return sorted(paths), "filesystem-fallback", problems


def module_name(rel: str) -> str:
    """Dotted module name for a repo-relative Python path."""
    stem = rel[:-4] if rel.endswith(".pyi") else rel[:-3]
    parts = stem.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def call_name(func: ast.expr) -> str | None:
    """Dotted text for a call target (`print`, `engine.render`)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    return None


def has_main_guard(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.ops) == 1
            and isinstance(test.ops[0], MAIN_GUARD_OPS)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            return True
    return False


def package_parts(name: str, rel: str) -> list[str]:
    """The package a module's relative imports resolve against."""
    parts = name.split(".") if name else []
    if rel.endswith(("__init__.py", "__init__.pyi")):
        return parts
    return parts[:-1]


def resolve_from_import(
    pkg: list[str], level: int, module: str | None
) -> str | None:
    """Resolve a `from ... import` target to a dotted name, or None."""
    if level == 0:
        return module or ""
    keep = len(pkg) - (level - 1)
    if keep < 0:
        return None
    tail = module.split(".") if module else []
    return ".".join(pkg[:keep] + tail)


def is_internal(target: str, modules: set[str]) -> bool:
    """True when the dotted import target resolves inside the repository."""
    if not target:
        return False
    if target in modules:
        return True
    prefix = target + "."
    return any(name.startswith(prefix) for name in modules)


def analyze_python(
    path: Path, rel: str, modules: set[str]
) -> tuple[dict | None, dict | None]:
    """AST-analyze one module.

    Returns ``(record, failure)``: exactly one is set. Failures carry the
    error class and line only — never source text.
    """
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=rel)
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        return None, {"path": rel, "error": type(exc).__name__, "line": line}

    name = module_name(rel)
    pkg = package_parts(name, rel)

    definitions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            definitions.append({"name": node.name, "kind": kind, "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            definitions.append({"name": node.name, "kind": "class", "line": node.lineno})
    local_defs = {d["name"] for d in definitions}

    internal: set[str] = set()
    other: set[str] = set()
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if is_internal(target, modules):
                    internal.add(target)
                else:
                    other.add(target)
        elif isinstance(node, ast.ImportFrom):
            target = resolve_from_import(pkg, node.level, node.module)
            if target is None:
                other.add("." * node.level + (node.module or ""))
                continue
            names_internal = any(
                is_internal(f"{target}.{alias.name}", modules) for alias in node.names
            )
            if is_internal(target, modules) or names_internal:
                internal.add(target)
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{target}.{alias.name}"
            else:
                other.add(target)

    calls = []
    functions: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append((f"{node.name}.{item.name}", item))
    for fname, fnode in functions:
        found: set[str] = set()
        for sub in ast.walk(fnode):
            if isinstance(sub, ast.Call):
                called = call_name(sub.func)
                if called:
                    found.add(called)
        ordered = sorted(found)
        truncated = len(ordered) > MAX_CALLS_PER_FUNCTION
        ordered = ordered[:MAX_CALLS_PER_FUNCTION]
        resolved = {}
        for called in ordered:
            if "." not in called and called in local_defs:
                resolved[called] = f"{name}.{called}"
            elif "." not in called and called in bindings:
                resolved[called] = bindings[called]
            elif "." in called:
                base, _, rest = called.partition(".")
                if base in bindings:
                    resolved[called] = f"{bindings[base]}.{rest}"
        entry = {
            "function": fname,
            "line": fnode.lineno,
            "calls": ordered,
            "resolved": resolved,
        }
        if truncated:
            entry["truncated"] = True
        calls.append(entry)

    doc = ast.get_docstring(tree) or ""
    record = {
        "name": name,
        "path": rel,
        "doc": doc.splitlines()[0] if doc else "",
        "definitions": definitions,
        "internal_imports": sorted(internal),
        "other_imports": sorted(other),
        "import_fan_out": len(internal | other),
        "calls": calls,
        "main_guard": has_main_guard(tree),
    }
    return record, None


def analyze_script(path: Path) -> dict:
    """Best-effort lexical scan of one JavaScript/TypeScript file."""
    imports: set[str] = set()
    exports: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = IMPORT_RE.match(line)
        if match:
            imports.add(match.group(1) or match.group(2))
        match = EXPORT_RE.match(line)
        if match:
            exports.add(match.group(1))
    return {"imports": sorted(imports), "exports": sorted(exports)}


def pyproject_entry_points(root: Path, problems: list[str]) -> list[dict]:
    """Entry points declared in the root pyproject.toml, if any."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        problems.append(
            f"pyproject.toml could not be parsed ({type(exc).__name__}): "
            "packaging-declared entry points are not determinable"
        )
        return []
    project = data.get("project", {})
    if not isinstance(project, dict):
        return []
    found = []
    for table, kind in (
        ("scripts", "pyproject-script"),
        ("gui-scripts", "pyproject-gui-script"),
    ):
        entries = project.get(table, {})
        if isinstance(entries, dict):
            for name, target in sorted(entries.items()):
                found.append(
                    {
                        "kind": kind,
                        "name": name,
                        "target": target,
                        "source": "pyproject.toml",
                    }
                )
    return found


def package_json_entry_points(root: Path, problems: list[str]) -> list[dict]:
    """Entry points declared in the root package.json, if any (best effort)."""
    path = root / "package.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        problems.append(
            f"package.json could not be parsed ({type(exc).__name__}): "
            "script entry points are not determinable"
        )
        return []
    if not isinstance(data, dict):
        return []
    found = []
    main = data.get("main")
    if isinstance(main, str):
        found.append(
            {"kind": "package-json-main", "target": main, "source": "package.json"}
        )
    bins = data.get("bin")
    if isinstance(bins, str):
        found.append(
            {
                "kind": "package-json-bin",
                "name": data.get("name", ""),
                "target": bins,
                "source": "package.json",
            }
        )
    elif isinstance(bins, dict):
        for name, target in sorted(bins.items()):
            found.append(
                {
                    "kind": "package-json-bin",
                    "name": name,
                    "target": target,
                    "source": "package.json",
                }
            )
    return found


def crawl(root: Path, max_files: int) -> dict:
    """Run the crawl and return the JSON report (no clock fields)."""
    candidates: list[str] = []
    census: dict[str, int] = {}
    oversized: list[str] = []
    symlinks = 0
    unreadable_dirs: list[str] = []
    selected, selection, problems = inventory(root)
    available: set[str] = set()
    for rel in selected:
        path = root / rel
        if any(part in IGNORE_DIRS for part in Path(rel).parts[:-1]):
            continue
        if any(parent.is_symlink() for parent in path.parents
               if parent != root and root in parent.parents):
            symlinks += 1
            continue
        suffix = path.suffix.lower()
        if path.is_symlink():
            census[suffix or "(no extension)"] = census.get(suffix or "(no extension)", 0) + 1
            symlinks += 1
            continue
        if path.is_dir():
            problems.append(
                f"directory inventory boundary not traversed: {rel} "
                "(submodule or nested repository)"
            )
            continue
        try:
            info = path.stat()
        except OSError:
            unreadable_dirs.append(rel)
            continue
        if not stat.S_ISREG(info.st_mode):
            problems.append(f"non-regular file not read: {rel}")
            continue
        size = info.st_size
        census[suffix or "(no extension)"] = census.get(suffix or "(no extension)", 0) + 1
        if size > MAX_FILE_BYTES:
            if suffix in SOURCE_SUFFIXES:
                oversized.append(rel)
            continue
        available.add(rel)
        if suffix in SOURCE_SUFFIXES:
            candidates.append(rel)

    candidates.sort()
    parsed = candidates[:max_files]
    beyond = len(candidates) - len(parsed)
    cap_reached = beyond > 0

    # First pass: discover the module namespace so imports resolve internally.
    module_names: set[str] = set()
    for rel in parsed:
        if rel.endswith(tuple(PY_SUFFIXES)):
            module_names.add(module_name(rel))

    py_modules: list[dict] = []
    unparsed: list[dict] = []
    ts_files: list[dict] = []
    js_files: list[dict] = []
    for rel in parsed:
        path = root / rel
        if rel.endswith(tuple(PY_SUFFIXES)):
            record, failure = analyze_python(path, rel, module_names)
            if record is not None:
                py_modules.append(record)
            else:
                unparsed.append(failure)
                eprint(
                    f"warning: could not parse {rel} ({failure['error']}); "
                    "reported as unparsed"
                )
        else:
            try:
                findings = analyze_script(path)
            except OSError as exc:
                unparsed.append(
                    {"path": rel, "error": type(exc).__name__, "line": None}
                )
                continue
            findings["path"] = rel
            if rel.endswith(tuple(TS_SUFFIXES)):
                ts_files.append(findings)
            else:
                js_files.append(findings)

    py_modules.sort(key=lambda m: m["name"])
    ts_files.sort(key=lambda f: f["path"])
    js_files.sort(key=lambda f: f["path"])
    unparsed.sort(key=lambda f: f["path"])

    entry_points = pyproject_entry_points(root, problems) if "pyproject.toml" in available else []
    if "package.json" in available:
        entry_points += package_json_entry_points(root, problems)
    for record in py_modules:
        if record["main_guard"]:
            entry_points.append({"kind": "python-main-guard", "path": record["path"]})
        if record["path"].endswith(("__main__.py", "__main__.pyi")):
            entry_points.append({"kind": "python-dunder-main", "path": record["path"]})
    entry_points.sort(key=lambda e: (e["kind"], e.get("path", ""), e.get("name", "")))

    if py_modules and "pyproject.toml" not in available:
        problems.append(
            "no selected readable pyproject.toml: packaging-declared Python entry points "
            "are not determinable"
        )
    if (ts_files or js_files) and "package.json" not in available:
        problems.append(
            "no selected readable package.json: script entry points are not determinable"
        )
    if oversized:
        problems.append(
            f"{len(oversized)} source file(s) over the 1 MiB parse limit, "
            f"counted only: {', '.join(sorted(oversized))}"
        )
    if cap_reached:
        problems.append(
            f"file cap reached: parsed {len(parsed)} of {len(candidates)} source "
            f"files in sorted path order; the remaining {beyond} were counted only"
        )
    for item in sorted(unreadable_dirs):
        problems.append(f"could not read: {item} (counted only)")
    if symlinks:
        problems.append(f"{symlinks} symlinked file(s) skipped (not followed)")

    return {
        "schema": SCHEMA,
        "tool": TOOL_PATH,
        "source": {
            "root": ".",
            "revision": source_revision(root),
            "selection": selection,
            "max_files": max_files,
            "cap_reached": cap_reached,
            "source_files_found": len(candidates),
            "source_files_parsed": len(parsed),
        },
        "census": dict(sorted(census.items())),
        "python": {"modules": py_modules, "unparsed": unparsed},
        "best_effort": {"typescript": ts_files, "javascript": js_files},
        "entry_points": entry_points,
        "not_determined": problems,
    }


def fmt_confirmed(target: str, source: str) -> str:
    return f"`{target}` (confirmed: {source})"


def render_markdown(report: dict, generated_at: str) -> str:
    """Render the CODEBASE.md artifact from a report. Bounded output."""
    lines: list[str] = []
    add = lines.append
    src = report["source"]
    revision = src["revision"] or "unknown (not a git repository)"

    add("# CODEBASE.md — generated codebase map")
    add("")
    add(f"> Generated by sf-crawl (`{TOOL_PATH}`). Do not hand-edit; regenerate")
    add("> with `python3 <skill-dir>/scripts/crawl.py .` from the repository root")
    add("> (`<skill-dir>` is the installed skill directory, e.g. `.claude/skills/sf-crawl`")
    add("> or `.agents/skills/sf-crawl`).")
    add("")
    add(f"- Source revision: {revision}")
    add(f"- File selection: {src['selection']}")
    add(f"- Generated: {generated_at}")
    add("")

    add("## Limits")
    add("")
    add("- Full treatment (Python, `ast`): module map, import edges, call edges,")
    add("  entry points. Project code is parsed, never executed or imported.")
    add("- Best effort (JavaScript/TypeScript): lexical patterns only — import")
    add("  specifiers and exported names. No type resolution; dynamic `import()`,")
    add("  computed `require` and re-export chains are missed. Everything else is")
    add("  counted by extension, not parsed.")
    add("- Static analysis cannot see runtime wiring (decorators, import hooks,")
    add("  framework route tables, dependency injection). What it cannot see is")
    add('  reported under "Not determined", never inferred.')
    add("- Calls inside nested functions are attributed to the enclosing")
    add("  top-level function or method.")
    add("- Ignored directories include `.git`, `node_modules`, virtualenvs,")
    add("  caches, `dist`, `build`, `target`, `vendor` and the factory's own")
    add("  `.software-factory` (the full list lives in the skill's coverage")
    add("  reference). Symlinks are not followed; files over 1 MiB are counted,")
    add("  not parsed.")
    add(
        f"- Bounds: at most {src['max_files']} source files are parsed in sorted"
    )
    add("  path order; tables are capped and the remainder is counted and stated.")
    add("  Every fact below is marked confirmed (a path, count or command is")
    add("  cited) or unconfirmed. Nothing is estimated silently.")
    if src["cap_reached"]:
        add(
            f"- Cap reached: parsed {src['source_files_parsed']} of"
            f" {src['source_files_found']} source files (sorted path order); the"
            " rest were counted only."
        )
    add("")

    modules = report["python"]["modules"]
    add("## Module map (Python)")
    add("")
    if not modules:
        add("No Python source found.")
    else:
        add("| Module | File | Definitions | Internal imports | Import fan-out |")
        add("| --- | --- | --- | --- | --- |")
        for record in modules[:MAX_MODULE_ROWS]:
            add(
                f"| `{record['name']}` | `{record['path']}` "
                f"| {len(record['definitions'])} "
                f"| {len(record['internal_imports'])} "
                f"| {record['import_fan_out']} |"
            )
        if len(modules) > MAX_MODULE_ROWS:
            add(f"| … | {len(modules) - MAX_MODULE_ROWS} more modules (cap reached) | | | |")
    add("")

    add("## Import edges (Python)")
    add("")
    if not modules:
        add("No Python source found.")
    else:
        edges = [
            (m["name"], target, m["path"])
            for m in modules
            for target in m["internal_imports"]
        ]
        if not edges:
            add("No internal import edges.")
        for name, target, path in edges:
            add(f"- `{name}` imports {fmt_confirmed(target, path)}")
    add("")

    add("## Call edges (Python)")
    add("")
    if not modules:
        add("No Python source found.")
    else:
        call_rows = [
            (m, c) for m in modules for c in m["calls"] if c["calls"]
        ]
        if not call_rows:
            add("No call edges extracted.")
        for record, entry in call_rows[:MAX_CALL_ROWS]:
            rendered = []
            for called in entry["calls"]:
                target = entry["resolved"].get(called)
                if target:
                    rendered.append(fmt_confirmed(called, target))
                else:
                    rendered.append(f"`{called}` (unconfirmed)")
            joined = ", ".join(rendered)
            suffix = " … (call cap reached)" if entry.get("truncated") else ""
            add(
                f"- `{record['name']}.{entry['function']}` (line {entry['line']})"
                f" calls {joined}{suffix}"
            )
        if len(call_rows) > MAX_CALL_ROWS:
            add(f"- … {len(call_rows) - MAX_CALL_ROWS} more call rows (cap reached)")
    add("")

    add("## Entry points")
    add("")
    if not report["entry_points"]:
        add("No entry points detected.")
    for entry in report["entry_points"]:
        kind = entry["kind"]
        if kind in ("pyproject-script", "pyproject-gui-script"):
            add(
                f"- `{entry['name']}` → `{entry['target']}` — confirmed:"
                f" pyproject.toml `[project.{'gui-scripts' if 'gui' in kind else 'scripts'}]`"
            )
        elif kind == "python-main-guard":
            add(f"- `__main__` guard — confirmed: `{entry['path']}`")
        elif kind == "python-dunder-main":
            add(f"- module execution — confirmed: `{entry['path']}`")
        elif kind == "package-json-main":
            add(
                f"- `{entry['target']}` — confirmed: package.json `main`"
                " (best effort)"
            )
        elif kind == "package-json-bin":
            add(
                f"- `{entry['name']}` → `{entry['target']}` — confirmed:"
                " package.json `bin` (best effort)"
            )
    add("")

    add("## Best effort (JavaScript/TypeScript)")
    add("")
    ts = report["best_effort"]["typescript"]
    js = report["best_effort"]["javascript"]
    if not ts and not js:
        add("No JavaScript/TypeScript files.")
    else:
        add("Lexical findings only (see Limits); specifiers are as written, not")
        add("resolved to files.")
        add("")
        add("| File | Imports | Exports |")
        add("| --- | --- | --- |")
        rows = ts + js
        for item in rows[:MAX_BEST_EFFORT_ROWS]:
            imports = ", ".join(f"`{i}`" for i in item["imports"]) or "—"
            exports = ", ".join(f"`{e}`" for e in item["exports"]) or "—"
            add(f"| `{item['path']}` | {imports} | {exports} |")
        if len(rows) > MAX_BEST_EFFORT_ROWS:
            add(f"| … | {len(rows) - MAX_BEST_EFFORT_ROWS} more files (cap reached) | |")
    add("")

    add("## Files not parsed")
    add("")
    if not report["python"]["unparsed"]:
        add("Everything parsed cleanly.")
    for failure in report["python"]["unparsed"]:
        where = f" (line {failure['line']})" if failure.get("line") else ""
        add(f"- `{failure['path']}` — {failure['error']}{where}")
    add("")

    add("## Not determined")
    add("")
    if not report["not_determined"]:
        add("Nothing was left undetermined.")
    for problem in report["not_determined"]:
        add(f"- {problem}.")
    add("")

    add("## File census")
    add("")
    total = sum(report["census"].values())
    ranked = sorted(report["census"].items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ", ".join(f"`{ext}` {count}" for ext, count in ranked[:MAX_CENSUS_ROWS])
    if len(ranked) > MAX_CENSUS_ROWS:
        rest = sum(count for _, count in ranked[MAX_CENSUS_ROWS:])
        shown += f", … {rest} more file(s) (cap reached)"
    add(f"{total} file(s) crawled. Counts by extension: {shown or 'none'}.")
    add("")
    return "\n".join(lines)


def write_atomic(path: Path, content: str) -> None:
    """Same-directory temp file, then an atomic replace. No backups."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=".CODEBASE.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            tmp.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crawl.py",
        description=(
            "Deterministic read-only codebase crawl: regenerates CODEBASE.md "
            "(default <root>/" + DEFAULT_ARTIFACT + ") and optionally writes a "
            "JSON report. Standard library only; never executes project code."
        ),
    )
    parser.add_argument("root", help="repository root to crawl (read-only)")
    parser.add_argument(
        "--json",
        dest="json_path",
        metavar="PATH",
        help="also write the machine-readable report to PATH ('-' for stdout)",
    )
    parser.add_argument(
        "--artifact",
        metavar="PATH",
        help=f"artifact path (default <root>/{DEFAULT_ARTIFACT})",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=f"source-file parse cap (default {DEFAULT_MAX_FILES})",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        eprint(f"error: root '{args.root}' is missing or not a directory")
        return 2
    root = root.resolve()

    report = crawl(root, max(1, args.max_files))

    if args.json_path:
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.json_path == "-":
            sys.stdout.write(payload)
        else:
            Path(args.json_path).write_text(payload, encoding="utf-8")

    artifact = (
        Path(args.artifact) if args.artifact else root / DEFAULT_ARTIFACT
    )
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        write_atomic(artifact, render_markdown(report, generated_at))
    except OSError as exc:
        eprint(f"error: could not write artifact: {exc}")
        return 2

    modules = len(report["python"]["modules"])
    entries = len(report["entry_points"])
    unparsed = len(report["python"]["unparsed"])
    eprint(
        f"wrote {artifact} ({modules} modules, {entries} entry points, "
        f"{unparsed} unparsed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
