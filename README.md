# Software Factory

![Software Factory: eleven skills and eleven role prompts for planning, building, proving and delivering through your coding host.](assets/hero.png)

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

[Launch image inventory and regeneration](docs/launch-assets.md).

## What's inside

- **11 skills** - `software-factory` (the orchestrator), `sf-help` (onboarding interview),
  `sf-agents` (agent registry and routing), `sf-evolve` (fold in new skills over time), the
  design set (`sf-design`, `sf-smell-audit`, `sf-refactor`, `sf-patterns`), `sf-eval`
  (eval-first suites and story evals), `sf-principles` (core principles and the project
  context home), and `sf-crawl` (read-only codebase crawl).
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

<!-- setup-prompts:start -->

### Copy a setup prompt

Use a trusted local pack checkout. Replace `<this-project>` with the intended project path.
The complete prompts below match the showcase's host selector.

#### Claude Code

```text
Set up Software Factory in this project for Claude Code using an existing trusted local checkout of the pack. Read its README, AGENTS.md and installer help first. Use Python 3.11+ on a POSIX system; native Windows helper execution is unverified.

From the pack checkout, inspect the proposed project install with:
python3 install.py install --host claude-code --skip-bmad --project <this-project> --dry-run
Then perform the reviewed local install with the same arguments without --dry-run. Preserve existing project files and host trust settings. BMad is optional and excluded from this first setup.

Invoke /software-factory and use sf-help to discover project context, prefill its twenty grouped decisions, and present the exact setup proposal for owner approval before applying it. Keep optional review bots and monitoring disabled until separately scoped and approved.

Then ground one useful first story, define accepted assertions and independent proof, and continue the authorized delivery loop. Record real evidence and unknowns; ask only about unresolved material scope, risk or authority. Keep the human epic checkpoint and actual host permissions in force.
```

#### Cursor

```text
Set up Software Factory in this project for Cursor using an existing trusted local checkout of the pack. Read its README, AGENTS.md and installer help first. Use Python 3.11+ on a POSIX system; native Windows helper execution is unverified.

From the pack checkout, inspect the proposed project install with:
python3 install.py install --host cursor --skip-bmad --project <this-project> --dry-run
Then perform the reviewed local install with the same arguments without --dry-run. Preserve existing project files and host trust settings. BMad is optional and excluded from this first setup.

Invoke /software-factory and use sf-help to discover project context, prefill its twenty grouped decisions, and present the exact setup proposal for owner approval before applying it. Keep optional review bots and monitoring disabled until separately scoped and approved.

Then ground one useful first story, define accepted assertions and independent proof, and continue the authorized delivery loop. Record real evidence and unknowns; ask only about unresolved material scope, risk or authority. Keep the human epic checkpoint and actual host permissions in force.
```

#### Codex

```text
Set up Software Factory in this project for Codex using an existing trusted local checkout of the pack. Read its README, AGENTS.md and installer help first. Use Python 3.11+ on a POSIX system; native Windows helper execution is unverified.

From the pack checkout, inspect the proposed project install with:
python3 install.py install --host codex --skip-bmad --project <this-project> --dry-run
Then perform the reviewed local install with the same arguments without --dry-run. Preserve existing project files and host trust settings. BMad is optional and excluded from this first setup.

Invoke $software-factory and use sf-help to discover project context, prefill its twenty grouped decisions, and present the exact setup proposal for owner approval before applying it. Keep optional review bots and monitoring disabled until separately scoped and approved.

Then ground one useful first story, define accepted assertions and independent proof, and continue the authorized delivery loop. Record real evidence and unknowns; ask only about unresolved material scope, risk or authority. Keep the human epic checkpoint and actual host permissions in force.
```

<!-- setup-prompts:end -->

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
