"""A tiny standard-library consumer behavior."""
from __future__ import annotations

import sys


def greeting(name: str = "world") -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a nonempty string")
    return f"Hello, {name.strip()}."


if __name__ == "__main__":
    try:
        print(greeting(sys.argv[1] if len(sys.argv) > 1 else "world"))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc
