#!/usr/bin/env python3
"""Render every Mermaid diagram in the tree and fail on any error.

Scope: tracked ``*.mmd`` files plus fenced ```mermaid blocks in tracked
Markdown (via ``git ls-files`` when the root is a git work tree, otherwise
a directory walk). Each diagram is rendered with the pinned Mermaid CLI
through ``npx`` into a temporary directory. The check never reports a
pass it did not verify: when the renderer is unavailable the diagrams are
reported as unverified and the exit code is nonzero.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FENCE_OPEN_RE = re.compile(r"^\s*```mermaid\s*$")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

MERMAID_PACKAGE = "@mermaid-js/mermaid-cli@11.17.0"
RENDER_TIMEOUT = 300

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".ruff_cache", ".venv"}


def tracked_files(root: Path) -> list[Path] | None:
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
    return [root / line for line in result.stdout.splitlines() if line.strip()]


def walk_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if set(path.relative_to(root).parts) & SKIP_DIRS:
            continue
        if path.name.endswith((".md", ".mmd")):
            found.append(path)
    return found


def fenced_blocks(text: str, label: str) -> list[tuple[str, str]]:
    """Extract fenced ```mermaid blocks from Markdown text."""
    diagrams: list[tuple[str, str]] = []
    lines = text.splitlines()
    index = 0
    block_no = 0
    while index < len(lines):
        if FENCE_OPEN_RE.match(lines[index]):
            block_no += 1
            start = index
            index += 1
            body: list[str] = []
            while index < len(lines) and not FENCE_CLOSE_RE.match(lines[index]):
                body.append(lines[index])
                index += 1
            diagrams.append(
                (f"{label} (block {block_no}, line {start + 1})", "\n".join(body))
            )
        index += 1
    return diagrams


def collect_diagrams(root: Path) -> list[tuple[str, str]]:
    """Return (label, mermaid source) pairs for every diagram in scope."""
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    else:
        files = [path for path in files if path.name.endswith((".md", ".mmd"))]
    diagrams: list[tuple[str, str]] = []
    for path in sorted(set(files)):
        if not path.is_file():
            continue
        label = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".mmd":
            diagrams.append((label, text))
        else:
            diagrams.extend(fenced_blocks(text, label))
    return diagrams


def render(npx: str, source: str, workdir: Path, tag: str) -> tuple[bool, str]:
    """Render one diagram; returns (ok, error output)."""
    src = workdir / f"{tag}.mmd"
    out = workdir / f"{tag}.svg"
    src.write_text(source, encoding="utf-8")
    try:
        result = subprocess.run(
            [npx, "-y", MERMAID_PACKAGE, "-i", str(src), "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"renderer failed to run: {exc}"
    if result.returncode != 0 or not out.is_file():
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = "\n".join(detail[-5:]) if detail else "no renderer output"
        return False, tail
    return True, ""


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

    if args.paths:
        diagrams: list[tuple[str, str]] = []
        for item in args.paths:
            item = item.resolve()
            if item.is_dir():
                diagrams.extend(collect_diagrams(item))
            elif item.is_file():
                text = item.read_text(encoding="utf-8", errors="replace")
                if item.suffix == ".mmd":
                    diagrams.append((item.name, text))
                else:
                    diagrams.extend(fenced_blocks(text, item.name))
            else:
                print(f"check_mermaid: '{item}' does not exist")
                return 2
        root_label = "explicit paths"
    else:
        root = args.root.resolve()
        if not root.is_dir():
            print(f"check_mermaid: root '{root}' is not a directory")
            return 2
        diagrams = collect_diagrams(root)
        root_label = str(root)

    if not diagrams:
        print(f"ok: no Mermaid diagrams found under {root_label}")
        return 0

    npx = shutil.which("npx")
    if npx is None:
        print(
            f"check_mermaid: unverified - npx (for {MERMAID_PACKAGE}) is not "
            f"available; {len(diagrams)} diagram(s) NOT rendered"
        )
        return 2

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sf-mermaid-") as tmp:
        workdir = Path(tmp)
        for index, (label, source) in enumerate(diagrams):
            ok, detail = render(npx, source, workdir, f"diagram-{index}")
            if ok:
                print(f"rendered: {label}")
            else:
                print(f"error: {label}: diagram failed to render\n{detail}")
                failures.append(label)
    if failures:
        print(f"check_mermaid: {len(failures)} of {len(diagrams)} diagram(s) failed")
        return 1
    print(f"ok: rendered {len(diagrams)} Mermaid diagram(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
