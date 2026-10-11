# 0005 — Standard-library Python installer with a thin shell bootstrap

Status: accepted · 2026-10-11

## Context

Installation must be safe on any consumer machine: structured file
transactions, JSON merges, backups and a conditional uninstall.

## Drivers

- The kernel helpers already require Python >= 3.11.
- No second runtime in the critical path; no global installs or sudo.

## Options

- A Node installer: BMad tooling needs Node, but the core would gain a
  runtime dependency for every user.
- A Bash-only installer: poor at safe structured merge and uninstall.
- `install.py` in stdlib Python; `install.sh` only fetches, verifies and
  invokes it.

## Outcome

The installer is standard-library Python with a thin POSIX bootstrap,
because Python is already the pack's runtime and handles transactions and
TOML/JSON without new dependencies.

## Consequences

- macOS/Linux with Python >= 3.11; no Windows lock emulation in v1.
- JSON-Schema-subset validation is cross-checked with a dev-only mature
  validator.

## Confirmation

- Installer unit and golden tests in temporary repositories (installer
  milestone); `python3 -m compileall` and pinned ruff in the gate.
