# Security Policy

## Reporting a vulnerability

Report privately through GitHub's private security advisories:

1. Open https://github.com/sbeeredd04/software-factory/security/advisories/new
   (the repository's Security tab, "Report a vulnerability").
2. Include the affected file or command, a reproduction, and the impact you see.

**Please do not open a public issue for a vulnerability.** If you are unsure whether something
is a vulnerability, report it privately anyway - a false alarm costs nothing.

What happens after you report:

- We acknowledge the report within 3 days.
- We assess impact and severity within 7 days and tell you the plan.
- Fixes are prioritized by severity. The advisory is published after a fix ships, with credit
  to you unless you prefer to remain anonymous.

## Supported versions

| Version | Supported |
| --- | --- |
| Default branch (`main`) | Yes |
| Latest tagged release | Yes |
| Older tagged releases | No |

Before the first tagged release, the default branch is the only supported version.

## Scope

In scope - the code this repository ships:

- `install.py` and `install.sh`: the installer and its bootstrap.
- The kernel helpers under `skills/software-factory/scripts/` (`state.py`, `gate.py`,
  `hook.py`, `config.py`).
- Hook wiring and every host projection the installer generates.
- The validation and scanning scripts under `scripts/`.
- The CI workflows and the release pipeline (supply chain).

Also in scope, with lower expected severity: prompt-injection-style weaknesses in shipped skill
and role text. Prompts and hooks are documented as assistant guidance, not as a security
boundary; text that could nonetheless lead an agent into unsafe behavior is a reportable issue.

Out of scope:

- Vulnerabilities in the hosts (Claude Code, Cursor, Codex) - report to their vendors.
- Vulnerabilities in BMad Method or in third-party skills folded in with `sf-evolve` - report
  upstream; this repository ships none of their code.
- Your own project's configuration, principles, or generated review-bot configs.
- Anything exploitable only through settings you deliberately changed to bypass the pack's
  guarantees.

## How the pack is designed to fail safe

- Shipped Python is standard-library-only (Python >= 3.11) with no model calls, no network
  calls, and no telemetry.
- The installer never uses sudo, never touches your home-directory host configurations, backs
  up before every overwrite, and uninstalls only files it owns that are unchanged.
- Hooks are inert without an active run pointer and never interpolate request text into
  commands.
- The bootstrap script verifies the checksum of any release archive it downloads before
  running the installer.
