# CLAUDE.md

Pointer file: the single source of contributor guidance is [AGENTS.md](AGENTS.md). Read it
first - it covers the repository map, the commands, the hard boundaries, and the writing style.

- [AGENTS.md](AGENTS.md) - what this repository is and how to work in it
- [CONTRIBUTING.md](CONTRIBUTING.md) - setup, the verification gate, conventions, and the
  fold-in path for new skills
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md), [NOTICE.md](NOTICE.md) -
  conduct, security reporting, attribution

House reminders that are easy to get wrong:

- Never run the `claude`, `cursor-agent`, or `codex` CLIs here, not even `--version`.
- Run `bash scripts/check_all.sh` before handing off any change, and report its real results.
- Never push directly to `main`, never force-push; pull requests target the integration branch
  `dev`.

Keep this file a pointer. When guidance changes, update [AGENTS.md](AGENTS.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) instead of adding content here.
