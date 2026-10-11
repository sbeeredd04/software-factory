# Recovery, checkpoints and the state helper

Phase: recovery — surviving context resets, interruptions and uncertain states.

The per-story board record owns story status and Git owns the code. The kernel
preserves local execution facts only: who owns which paths, what was decided,
what happens next. Its claims are the path-exclusivity system of record and its
checkpoints are recovery context — not a second live status store.

## When to checkpoint

Persist at meaningful transitions — dispatch, proof, integration, blocker,
decision — and before a context reset or a risky action. Ask workers for factual
handoffs and their running/stopped status before the human clears context; pause
new dispatch until a readable checkpoint exists. The note shape the helper
accepts (short fields, bounded lists, no secrets):

```json
{
  "objective": "Approved story and GO source",
  "completed": ["Verified SHA and evidence path"],
  "next": "One exact safe next action",
  "decisions": ["Decision ref; schedule rationale; owner/phase resource"],
  "open_questions": ["Uncertain outcome and its reconciliation action"]
}
```

## The state helper

Run from this skill's directory; `<project-root>` is the consumer project's
absolute root:

```sh
python3 scripts/state.py checkpoint --workspace "<project-root>" --notes "<notes.json>"
python3 scripts/state.py status --workspace "<project-root>"
```

Commands: `init` (start an authorized program; refuses a second one), `claim` /
`release` (exclusive repo-relative paths per owner), `checkpoint` (validated
notes), `snapshot` (read-only Git observations; a failed observation degrades to
`unknown`), `status` (read-only projection), `deactivate` (archives the pointer
once every claim is released), `repair` (restores a validated existing run after
a missing or corrupt pointer; never invents a run). `--help` prints the full
syntax. Refusals exit nonzero with one sanitized line and leave state untouched.

## Hooks

The installer wires `scripts/hook.py` into each host. On session start it emits
a short recovery pointer — where the checkpoint lives and that it is recovery
state, not a new authorization. On pre-compact it refreshes the Git snapshot.
Without an active program the hook is inert: no output, exit zero. A hook
showing a pointer never authorizes work by itself.

## Resume and reconciliation

On resume, re-read the principles, decisions, checkpoint, the board records and
their planning source, actual Git state and diffs, PRs, deploys, effects, live
workers and claims, and evidence freshness. Saved notes are hints until
corroborated. Reconnect or steer
live owners; confirm a worker is stopped and reconcile its work and effects
before releasing or reclaiming its paths — no stale-owner expiry and no
duplicate redispatch. Preserve dirty user trees and conflicting receipts. An
unknown push, merge, deploy or external effect is inspected at the provider
before any retry. After a merge, retest the affected stories only. Continue only
an authorized program.

## Helper limits

Atomic writes and a local lock protect the run files; the lock is not a Git
lock, a distributed fence, a task lease or an effect ledger. Helpers do not
infer intent, choose models or prove artifact truth — independent review still
reads and runs the evidence. Installation creates no run state.
