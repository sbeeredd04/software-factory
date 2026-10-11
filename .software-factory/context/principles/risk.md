# Risk — Software Factory

Human owner: the repository maintainer (`@sbeeredd04` on GitHub). Every
escalation below goes to them with a recommendation, never a silent
decision.

## Risk tiers

- **Tier 0 — docs, prose, tests, fixtures.** Small spec, relevant proof.
- **Tier 1 — standard implementation.** Skills, scripts, tooling; the
  normal loop with its eval cases.
- **Tier 2 — sensitive mechanics.** Installer transactions, hook wiring,
  gate logic, state/lock handling, anything touching user files or
  settings; principal-engineer staffing and independent review.
- **Tier 3 — irreversible or outward-facing.** Publication, releases,
  history changes; human GO at the checkpoint before any step runs.

## Always escalate to the human owner

- Production writes or any change to a live, deployed surface.
- Auth, money, state-machine, migration or concurrency changes.
- Destructive operations on user work: deletes, force-pushes, history
  rewrites, broad cleanups.
- Policy or security changes: permission models, hook trust, gate rules.
- Credential or trust changes: tokens, scopes, new external services.
- Publishing: making the repository public, cutting a release, or any
  outward-facing announcement.

Tier scales ceremony — eval floors, review depth, checkpoint strictness —
and never removes the floor.
