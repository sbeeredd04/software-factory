#!/usr/bin/env python3
"""Offline relative-link and anchor check for Markdown and JSON files.

Scope: tracked ``*.md`` files (via ``git ls-files`` when the root is a git
work tree, otherwise a directory walk). Inline links, images and
reference-style definitions outside code fences are resolved against the
repository; fragment anchors are checked against GitHub-style heading
slugs. External ``https?://`` links are advisory only: they are counted
and never fail the run. JSON string values that start with ``./`` or
``../`` resolve from their file directory, or the owning root for known
native manifests, and must stay within the repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(\S+)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".ruff_cache", ".venv"}


def tracked_files(root: Path, suffixes: tuple[str, ...]) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [
        root / line
        for line in result.stdout.splitlines()
        if line.strip().endswith(suffixes)
    ]


def walk_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not path.name.endswith(suffixes):
            continue
        if set(path.relative_to(root).parts) & SKIP_DIRS:
            continue
        found.append(path)
    return found


def scope_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    files = tracked_files(root, suffixes)
    if files is None:
        files = walk_files(root, suffixes)
    return sorted(path for path in files if path.is_file())


def outside_fences(lines: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_fence = False
    for line_no, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((line_no, line))
    return out


def slugify(heading: str) -> str:
    """GitHub-style anchor slug for a heading."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return text.replace(" ", "-")


def anchors_of(path: Path) -> set[str]:
    slugs: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return slugs
    for _, line in outside_fences(lines):
        match = HEADING_RE.match(line)
        if match:
            slugs.add(slugify(match.group(1)))
    return slugs


def check_markdown(root: Path, problems: list[str]) -> tuple[int, int]:
    checked = 0
    external = 0
    anchor_cache: dict[Path, set[str]] = {}
    for md in scope_files(root, (".md",)):
        checked += 1
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            problems.append(f"{md.relative_to(root)}: unreadable: {exc}")
            continue
        targets: list[tuple[int, str]] = []
        for line_no, line in outside_fences(lines):
            targets.extend(
                (line_no, match.group(1).strip("<>"))
                for match in INLINE_LINK_RE.finditer(line)
            )
            ref = REFERENCE_DEF_RE.match(line)
            if ref:
                targets.append((line_no, ref.group(1)))
        for line_no, target in targets:
            if target.startswith(("mailto:", "tel:")):
                continue
            if target.startswith(("https://", "http://")):
                external += 1
                continue
            path_part, _, fragment = target.partition("#")
            if path_part:
                resolved = (md.parent / path_part).resolve()
                label = md.relative_to(root)
                if not resolved.is_relative_to(root.resolve()):
                    problems.append(f"{label}:{line_no}: '{target}' escapes the root")
                    continue
                if not resolved.exists():
                    problems.append(
                        f"{label}:{line_no}: target '{path_part}' does not exist"
                    )
                    continue
                target_file = resolved
            else:
                target_file = md
            if fragment and target_file.is_file() and target_file.suffix == ".md":
                if target_file not in anchor_cache:
                    anchor_cache[target_file] = anchors_of(target_file)
                if fragment not in anchor_cache[target_file]:
                    label = md.relative_to(root)
                    problems.append(
                        f"{label}:{line_no}: anchor '#{fragment}' not found in "
                        f"'{target_file.relative_to(root)}'"
                    )
    return checked, external


def check_json(root: Path, problems: list[str]) -> int:
    checked = 0
    for js in scope_files(root, (".json",)):
        checked += 1
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue  # not a link problem; the validator owns parse errors

        base = js.parent
        native = False
        if js.name in {"plugin.json", "marketplace.json"} and base.name in {
            ".claude-plugin", ".cursor-plugin"
        }:
            base = base.parent
            native = True
        elif (js.name == "marketplace.json" and base.name == "plugins"
              and base.parent.name == ".agents"):
            base = base.parent.parent
            native = True

        def walk(node: object, base: Path = base, source: Path = js,
                 native: bool = native) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value, base, source, native)
            elif isinstance(node, list):
                for value in node:
                    walk(value, base, source, native)
            elif isinstance(node, str) and node.startswith(("./", "../")):
                resolved = (base / node).resolve()
                if not resolved.is_relative_to(root.resolve()):
                    problems.append(f"{source.relative_to(root)}: '{node}' escapes the root")
                elif native and not resolved.is_relative_to(base.resolve()):
                    problems.append(f"{source.relative_to(root)}: '{node}' escapes its manifest root")
                elif not resolved.exists():
                    problems.append(
                        f"{source.relative_to(root)}: target '{node}' does not exist"
                    )

        walk(data)
    return checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to check (default: the whole root)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"check_links: root '{root}' is not a directory")
        return 2

    problems: list[str] = []
    if args.paths:
        # Explicit files or directories: check every Markdown file given
        # (or found under a given directory), resolving links relative to
        # each file. Still fully offline.
        checked = external = 0
        given: list[Path] = []
        for item in args.paths:
            item = item.resolve()
            if item.is_dir():
                given.extend(walk_files(item, (".md",)))
            elif item.is_file():
                given.append(item)
            else:
                problems.append(f"{item}: no such file or directory")
        for md in sorted(set(given)):
            c, e = _check_single(md, problems)
            checked += c
            external += e
    else:
        checked, external = check_markdown(root, problems)
        checked += check_json(root, problems)

    if problems:
        for problem in problems:
            print(f"error: {problem}")
        print(f"check_links: {len(problems)} broken link(s)")
        return 1
    print(
        f"ok: {checked} file(s) checked, {external} external link(s) advisory-only"
    )
    return 0


def _check_single(md: Path, problems: list[str]) -> tuple[int, int]:
    """Check one Markdown file standing alone (used for explicit paths)."""
    external = 0
    try:
        lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        problems.append(f"{md}: unreadable: {exc}")
        return 0, 0
    anchor_cache: dict[Path, set[str]] = {}
    for line_no, line in outside_fences(lines):
        for match in INLINE_LINK_RE.finditer(line):
            target = match.group(1).strip("<>")
            if target.startswith(("mailto:", "tel:")):
                continue
            if target.startswith(("https://", "http://")):
                external += 1
                continue
            path_part, _, fragment = target.partition("#")
            if path_part:
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    problems.append(
                        f"{md}:{line_no}: target '{path_part}' does not exist"
                    )
                    continue
                target_file = resolved
            else:
                target_file = md
            if fragment and target_file.is_file() and target_file.suffix == ".md":
                if target_file not in anchor_cache:
                    anchor_cache[target_file] = anchors_of(target_file)
                if fragment not in anchor_cache[target_file]:
                    problems.append(
                        f"{md}:{line_no}: anchor '#{fragment}' not found"
                    )
    return 1, external


if __name__ == "__main__":
    sys.exit(main())
