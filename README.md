# Software Factory

**BMad plans, the factory ships.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Software Factory is an open-source skill pack that turns a coding agent - Claude Code, Cursor,
or Codex - into an autonomous software factory. One orchestrator owns the whole loop:

1. **Ground** - read the project's principles, architecture, and conventions before acting.
2. **Plan** - BMad Method v6 (installed separately, pinned) drafts the PRD and epics.
3. **Staff** - route each task by risk, from a standard engineer up to a principal engineer
   for auth, money, state machines, migrations, and concurrency.
4. **Ship** - implement, test, and review in claimed worktrees; merge behind an evidence gate.
5. **Prove** - verification binds to a subject SHA; a health-check 200 is not proof.
6. **Checkpoint** - a human confirms each epic before the next one starts.

> **Status: pre-release, targeting v0.1.0.** This repository is under active development.
> [CHANGELOG.md](CHANGELOG.md) tracks what has landed.

## What's inside

- **8 skills** - `software-factory` (the orchestrator), `sf-help` (onboarding interview),
  `sf-agents` (agent registry and routing), `sf-evolve` (fold in new skills over time), and the
  design set: `sf-design`, `sf-smell-audit`, `sf-refactor`, `sf-patterns`.
- **11 role prompts** - product manager, architect, design reviewer, engineer, principal
  engineer, QA engineer, code reviewer, evaluator, AI engineer, release engineer, security
  reviewer. A starting team the orchestrator staffs from as needed, not a mandatory fleet.
- **A standard-library installer** - projects the pack into Claude Code, Cursor, and Codex with
  provenance hashes, backups, and a safe uninstall.
- **Kernel helpers** - claims, checkpoints, and evidence gates in Python >= 3.11, stdlib only:
  no model calls, no network calls, no telemetry.

## Install

Install instructions ship with the v0.1.0 release. The pack installs into your project - never
into your home directory - and adds no permission bypasses, no sudo, and no auto-updates.

## Community

- [Contributing](CONTRIBUTING.md) - setup, the verification gate, conventions, and the fold-in
  path for new skills
- [Code of conduct](CODE_OF_CONDUCT.md) - Contributor Covenant 2.1
- [Security](SECURITY.md) - report vulnerabilities privately
- [Changelog](CHANGELOG.md)
- [Notice](NOTICE.md) - attribution, trademarks, non-affiliation

## Compatibility

Software Factory works with Claude Code, Cursor, and Codex, and **Works with BMad Method v6**.
It is not affiliated with, endorsed by, or sponsored by Anthropic, Anysphere (Cursor), OpenAI,
GitHub, or the BMad Method maintainers. All product names are the property of their respective
owners.

## License

MIT - see [LICENSE](LICENSE). Copyright (c) 2026 sbeeredd04 and Software Factory contributors.
