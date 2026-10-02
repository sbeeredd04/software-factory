# Dispatch and isolation

Phase: dispatch — turning ready stories into staffed, isolated work.

## Preflight

Inspect the actual state before dispatching: repository root, remote identity,
Git common directory, HEAD, integration-branch ancestry, dirty and untracked
paths, and existing worktrees. In a multi-repo project, name which repository
each story targets; a worktree in the wrong repo is a common silent failure.

## Worktrees and claims

The orchestrator creates the exact target-repo story branch and worktree, and
claims its exclusive paths, before any worker writes. Do not rely on host
automatic worktree isolation; workers get absolute edit paths and an explicit
working directory. Claims run through the state helper, from this skill's
directory:

```sh
python3 scripts/state.py claim --workspace "<project-root>" \
  --task "<story-id>" --owner "<worker-attempt>" \
  --repo "<absolute-story-worktree>" \
  --paths "src/affected.py" "tests/test_affected.py"
```

One writer per conflicting path, including parent/child scopes across worktrees
that share a Git common dir. Worktrees isolate files only — not ports,
credentials, databases or external effects. A genuinely shared resource (schema
pins, migrations, ports, a staging test profile, environment writes) is held by
one contending phase at a time; a test-only resource does not serialize the
whole story. Record the resource owner and phase, and reconcile before reuse.

Claims do not expire automatically. Before releasing or redispatching, reconnect
the live owner or confirm it stopped, and reconcile its work and effects. Claims
protect owner/path collisions; they are not readiness, not a lease and not a
fence on external systems. No new scheduler, queue, daemon or workflow engine.

## Scheduling

Staff the approved ready frontier adaptively: serial, batches or continuous
backfill, chosen by coupling, best-fit capacity and observed failure and rework.
There is no fixed worker cap and no cheapest-first rule. A human question or
checkpoint blocks only its dependents. Record a one-line scheduling rationale in
briefs and checkpoint notes.

## Work and return

Brief each worker with outcome, fresh sources, contracts and deletions, scope
and authority, the exact repo and base SHA, dependency-unlock receipts,
exclusive paths, phase resources, acceptance criteria and the proof destination
— the template is in [handoff](handoff.md). Direction and evidence expectations
enable judgment; workers may use specialists or skills suited to the problem.

Workers return the actual diff and HEAD, changed paths, commands with exit
codes, verified effects and per-criterion results, plus uncertainty and one exact
next action. Verified findings from independent review and QA go back to the
owning worker as a fix loop. Diagnose stalls rather than retrying equivalents or
abandoning tasks. Checkpoint at dispatch, at proof, at blockers and at
decisions (see [recovery](recovery.md)).
