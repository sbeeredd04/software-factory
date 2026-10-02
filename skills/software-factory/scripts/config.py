"""Parse Software Factory configuration with the standard library only.

The v1 contract accepts the documented JSON-compatible subset of YAML: a
JSON document, which is itself valid YAML, in `.software-factory/config.yaml`.
Anything the documented rules cannot parse is refused with an explanation and
is never partially interpreted. Configuration is data: nothing found in it is
ever run by this helper.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class ConfigError(ValueError):
    pass


def parse(text):
    """Parse configuration text under the documented rules, or refuse it."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigError(
            "configuration is not valid JSON (the v1 JSON-compatible YAML subset); "
            f"refusing to interpret it partially ({exc.__class__.__name__})"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError("configuration must be an object at the top level")
    return data


def load(path):
    path = Path(path)
    try:
        text = path.read_text()
    except UnicodeDecodeError as exc:
        raise ConfigError("configuration file is not UTF-8 text") from exc
    except OSError as exc:
        raise ConfigError(f"configuration file unreadable: {path.name}") from exc
    return parse(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = load(args.config)
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1
    keys = ", ".join(sorted(data)) if data else "none"
    print(f"Configuration parsed: {len(data)} top-level keys ({keys}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
