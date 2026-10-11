# Product principles — Software Factory

What this is for: an MIT-licensed skill pack (Markdown plus standard-library
Python) that turns a coding agent — Claude Code, Cursor or Codex — into an
autonomous software factory. One orchestrator owns the loop from grounded
intent to planned work, evidence-gated merge, deploy proof and a human
checkpoint per epic. BMad Method v6, installed separately and pinned, does
the planning; the factory ships.

## Outcomes that matter

- A consumer can install the pack into a project and run a full feature lap
  with evidence at every gate, on any of the three hosts.
- Every claim the pack makes is verifiable offline: formats, installers and
  helpers are tested; live-host behavior is never asserted unverified.
- The pack proves itself: this repository runs on the method (this context
  home, the board, the eval suite) and its own gate runs its own evals.
- The public release is clean: no private names, paths, credentials or
  product decisions anywhere in tracked files, output or history.

## Non-goals

- No scheduler, daemon, model client, memory service or workflow engine.
- No telemetry, no auto-updates, no permission bypasses, no sudo.
- No vendored BMad content; BMad is installed by its own pinned installer.
- Not a hosted service and not a multi-repo or team-mode product in v0.1.
- Not a guarantee of host-vendor behavior the pack cannot test statically.
