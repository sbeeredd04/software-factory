# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Dates use the
ISO 8601 `YYYY-MM-DD` format.

## [Unreleased]

### Added

- Validation tooling under `scripts/`: `validate.py` (canonical layout of the
  eleven skills and eleven role agents from a single data constant, frontmatter
  budgets and standard keys, reference resolution, agent and manifest rules,
  clear quoting hints for the unquoted-colon frontmatter pitfall),
  `scan_public.py` (SHA-256 hashed denylist over tokens and n-grams plus
  length/context-gated path, secret and private-domain patterns; tracked-file
  scope with `--stdin`/`--history` modes; fails closed without a denylist),
  `check_links.py` (offline relative-link and anchor resolution), and
  `check_mermaid.py` (renders every diagram, never passes an unverified one),
  unified by the `scripts/check_all.sh` gate. Unit tests in
  `tests/test_tools.py`.
- Palette expansion to eleven skills: clearly marked placeholder entries for
  `sf-eval` (eval-first setup and story evaluation), `sf-principles` (core
  principles and the `.software-factory/context/` project-context home) and
  `sf-crawl` (read-only AST crawl producing `CODEBASE.md`), pending full
  authoring in the expansion milestone. The orchestrator skill, its team and
  verification references and the loop workflows now name the eleven-skill
  palette, the eval gate, the master-board update step and the context home,
  and the public-facing documents (README, AGENTS.md, the bug-report form)
  count the same eleven skills.
- The `software-factory` orchestrator skill: a host-neutral entry map, the
  feature and bug workflow graphs with prose walkthroughs, eleven phase
  references (team, planning, dispatch, verification, integration, recovery,
  configuration, authority, hosts, evidence, handoff), and clearly marked
  placeholder entries for `sf-help`, `sf-agents` and `sf-evolve` so the
  eleven-skill layout validates ahead of the onboarding milestone.
- Standard-library kernel helpers under `skills/software-factory/scripts/`: `state.py`
  (active-program pointer, exclusive path claims with Git common-dir identity and
  parent/child collision detection, checkpoint notes with shape limits, snapshot,
  read-only status, deactivate/repair; atomic writes and an `fcntl` state lock),
  `gate.py` (evidence-manifest validation with configuration-driven check names and a
  `deploy`/`deployed_sha` proof; reads data only), `hook.py` (session-start recovery
  pointer and pre-compact snapshot for Claude Code, Cursor and Codex with host-correct
  envelopes; inert without an active pointer) and `config.py` (fail-closed parsing of
  the documented JSON-compatible YAML subset; never executes configuration content).
- Unit tests for the kernel helpers (`tests/test_state.py`, `tests/test_gate.py`,
  `tests/test_hook.py`, `tests/test_config_kernel.py`) covering concurrency,
  worktree collisions, credential refusal, degraded Git observation and sanitized
  failure modes, with a shared fixture module (`tests/support.py`).

- Repository skeleton and community health files: MIT [LICENSE](LICENSE), [NOTICE.md](NOTICE.md)
  with attribution and trademark notices, [CONTRIBUTING.md](CONTRIBUTING.md),
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1), [SECURITY.md](SECURITY.md),
  this changelog, an [AGENTS.md](AGENTS.md) for contributors with a short [CLAUDE.md](CLAUDE.md)
  pointer, a [README.md](README.md), a `.gitignore`, GitHub issue forms (bug report, feature
  request, skill or integration contribution), a pull request template, a Dependabot
  configuration, and a CI workflow covering Linux and macOS across Python 3.11 to 3.13.

## [0.1.0]

Placeholder for the first tagged public release. When the tag is cut, the release entry is
dated in ISO 8601 format and filled in from the `[Unreleased]` section above.

### Added

- Initial public release of the Software Factory skill pack.
