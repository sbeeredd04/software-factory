#!/usr/bin/env python3
"""Public-cleanliness scanner for the Software Factory pack.

Two mechanisms, both offline and standard-library only:

1. A hashed denylist (``scripts/denylist.sha256``): candidate tokens and
   token n-grams from each scanned file are lowercased, hashed with
   SHA-256, and compared against the digests. Hits are reported with the
   digest, never the plaintext term.
2. Generic patterns that need no denylist: absolute user/home paths,
   length-gated secret shapes (token bodies must be plausibly long, and
   private-key headers must be followed by a base64 body line, so regex
   shapes in source and short synthetic test fixtures never self-flag),
   and private hosted-service domain shapes.

Scope: the tracked file set (``git ls-files``) plus ``dist/``, ``site/``
and ``assets/`` when present. The denylist file itself is never scanned.
Fails closed when the denylist is missing or malformed. ``--stdin`` (or
``--history -``) scans piped text, which is how history scans run.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")
NGRAM_MAX = 3
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

# Generic patterns. Each is (rule name, compiled regex). Patterns are
# length- or context-gated so plausible-looking but synthetic short
# fixtures and in-source regex shapes never flag. Pattern strings are
# assembled so this file does not match its own rules.
USERS_ROOT = "/Users/"
HOME_ROOT = "/home/"
GENERIC_LINE_PATTERNS = (
    (
        "absolute user path",
        re.compile(re.escape(USERS_ROOT) + r"[^/\s]+/"),
    ),
    (
        "absolute home path",
        re.compile(re.escape(HOME_ROOT) + r"[^/\s]+/"),
    ),
    (
        "windows user path",
        re.compile(r"[A-Za-z]:" + re.escape("\\") + r"Users" + re.escape("\\") + r"[^\\\s]+"),
    ),
    (
        "hosted database project domain",
        re.compile(r"\b[a-z0-9]{8,}\.supabase\.co\b"),
    ),
    (
        "hosted app domain",
        re.compile(r"\b[a-z0-9][a-z0-9-]*\.up\.railway\.app\b"),
    ),
)
SECRET_PATTERNS = (
    ("api token", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("git host token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("git host fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("cloud access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
PRIVATE_KEY_HEADER = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
PRIVATE_KEY_BODY = re.compile(r"^[A-Za-z0-9+/=]{20,}$")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".ruff_cache", ".venv"}
EXTRA_SCOPE_DIRS = ("dist", "site", "assets")


class ScanError(Exception):
    """The scan cannot run safely (missing or malformed inputs)."""


def load_denylist(path: Path) -> frozenset[str]:
    if not path.is_file():
        raise ScanError(
            f"denylist '{path}' is missing or unreadable; refusing to scan "
            "without it (fail closed)"
        )
    digests: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if not DIGEST_RE.fullmatch(entry):
            raise ScanError(
                f"denylist '{path}' line {line_no} is not a 64-hex SHA-256 "
                "digest; refusing to scan (fail closed)"
            )
        digests.add(entry)
    if not digests:
        raise ScanError(f"denylist '{path}' has no digests; refusing to scan")
    return frozenset(digests)


def tracked_files(root: Path) -> list[Path] | None:
    """Tracked files via git, or None when root is not a git work tree."""
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
        found.append(path)
    return found


def scope_files(root: Path, denylist: Path) -> list[Path]:
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    else:
        # dist/, site/ and assets/ may be git-ignored build output; scan
        # them explicitly when present.
        known = {path.resolve() for path in files}
        for extra in EXTRA_SCOPE_DIRS:
            extra_dir = root / extra
            if extra_dir.is_dir():
                for path in walk_files(extra_dir):
                    if path.resolve() not in known:
                        files.append(path)
    denylist_resolved = denylist.resolve()
    return [
        path
        for path in sorted(set(files))
        if path.is_file() and path.resolve() != denylist_resolved
    ]


def read_text_lossy(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None  # binary
    return raw.decode("utf-8", errors="replace")


def digest_of(candidate: str) -> str:
    return hashlib.sha256(candidate.encode()).hexdigest()


def scan_text(
    label: str, text: str, digests: frozenset[str], hits: list[str]
) -> None:
    lines = text.splitlines()

    # Generic per-line patterns.
    for line_no, line in enumerate(lines, 1):
        for rule, pattern in GENERIC_LINE_PATTERNS + SECRET_PATTERNS:
            if pattern.search(line):
                hits.append(f"{label}:{line_no}: {rule} pattern match")

    # Private-key blocks: a header alone (for example a regex shape in
    # source) is not a leak; a header followed by a base64 body line is.
    for index, line in enumerate(lines):
        if not PRIVATE_KEY_HEADER.search(line):
            continue
        for follow in lines[index + 1 : index + 40]:
            if "-----END" in follow:
                break
            if PRIVATE_KEY_BODY.match(follow.strip()):
                hits.append(f"{label}:{index + 1}: private key block")
                break
            if follow.strip() and not follow.startswith((" ", "\t")):
                break

    # Hashed denylist over tokens and n-grams.
    tokens: list[tuple[str, int]] = []
    for line_no, line in enumerate(lines, 1):
        tokens.extend((token, line_no) for token in TOKEN_RE.findall(line.lower()))
    for size in range(1, NGRAM_MAX + 1):
        for start in range(len(tokens) - size + 1):
            candidate = " ".join(token for token, _ in tokens[start : start + size])
            digest = digest_of(candidate)
            if digest in digests:
                line_no = tokens[start][1]
                hits.append(f"{label}:{line_no}: denylist match sha256={digest}")


def report(hits: list[str], scanned: int) -> int:
    if hits:
        for hit in hits:
            print(hit)
        print(f"scan_public: {len(hits)} hit(s) across {scanned} file(s)")
        return 1
    print(f"ok: scanned {scanned} file(s), no public-cleanliness hits")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to scan (default: current directory)",
    )
    parser.add_argument(
        "--denylist",
        type=Path,
        default=Path(__file__).resolve().with_name("denylist.sha256"),
        help="hashed denylist file (default: scripts/denylist.sha256)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="scan standard input instead of files (history scans)",
    )
    parser.add_argument(
        "--history",
        nargs="?",
        const="-",
        metavar="FILE",
        help="scan a history dump ('-' reads standard input)",
    )
    args = parser.parse_args(argv)

    try:
        digests = load_denylist(args.denylist)
    except ScanError as exc:
        print(f"scan_public: {exc}")
        return 2

    hits: list[str] = []
    if args.stdin or args.history is not None:
        if args.history not in (None, "-"):
            try:
                text = Path(args.history).read_text(encoding="utf-8")
            except OSError as exc:
                print(f"scan_public: cannot read '{args.history}': {exc}")
                return 2
        else:
            text = sys.stdin.read()
        scan_text("<stdin>", text, digests, hits)
        return report(hits, 1)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"scan_public: root '{root}' is not a directory")
        return 2
    files = scope_files(root, args.denylist)
    scanned = 0
    for path in files:
        text = read_text_lossy(path)
        if text is None:
            continue
        scanned += 1
        label = str(path.relative_to(root))
        scan_text(label, text, digests, hits)
    return report(hits, scanned)


if __name__ == "__main__":
    sys.exit(main())
