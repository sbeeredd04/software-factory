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
accepts (exactly the five keys below, strings of 1-500 characters, lists of at
most eight items, no secrets):

```json
{
  "objective": "Approved story and GO source",
  "completed": ["Verified SHA and evidence path"],
  "next": "One exact safe next action",
  "decisions": ["Decision ref; schedule rationale; owner/phase resource"],
  "open_questions": ["Uncertain outcome and its reconciliation action"]
}
```

## Compact done/next per step

Context degrades; the durable record must not. Every step ends in a compact,
re-readable record: the worker's own board record (status, receipts,
transition history), the bounded checkpoint note above, and a handoff that
ends in one exact next action (the shape is in [handoff](handoff.md)). The
board and the checkpoint on disk are the durable state — session memory is
not. Write each entry so a cold reader can resume from it; if a note would
not survive the session-start injection cap described under Hooks, it is too
long.

## The state helper

Run from this skill's directory; `<project-root>` is the consumer project's
absolute root:

```sh
python3 scripts/state.py checkpoint --workspace "<project-root>" --notes "<notes.json>"
python3 scripts/state.py status --workspace "<project-root>"
```

Commands: `init`, `claim` / `release`, `checkpoint`, `snapshot`, `status`,
`reconcile`, `audit`, `deactivate`, `repair` — `--help` prints the full
syntax. Refusals exit nonzero with one sanitized line and leave state
untouched.

## Hooks

The installer wires `scripts/hook.py` into each host. On session start it emits
a short recovery pointer — where the checkpoint lives and that it is recovery
state, not a new authorization. On pre-compact it refreshes the Git snapshot.
Without an active program the hook is inert: no output, exit zero. A hook
showing a pointer never authorizes work by itself.

The injection is bounded and content-aware: the pointer is capped at 1,500
characters, and the projection is ordered to survive that cap — header, then
the objective and the exact next action, then the bounded note lists, with the
per-claim rows last. A run with many claims or a long completed list truncates
history, never the objective or the next action. The injected text is a
pointer to the checkpoint on disk, never the full history.

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

## The board: records, transitions and projections

The master board lives in the committed context home at
`.software-factory/context/board/`: `streams.json` (the streams and their
epic order), `meta.json` (the id counters), `epics/<id>.json` (outcome,
done-when list, covered requirement ids, explicit build `order`, declared
cross-epic `needs`, status) and `stories/<id>.json` — one live record per
story carrying its id, epic, type (`story | bug | spike`), title, status,
owner, `after` prerequisites, `covers` ids, risk, the human-checkpoint
fields (`hitl`, `plan_checkpoint`, `done_checkpoint`), the `blocked` overlay,
receipts, branch/baseline/PR/merge fields and a transition history. The
normative record contract is `schemas/board.schema.json`; every record is
validated at generation. Ids are integers assigned once and never reused,
joins are by id and never by filename (a title rename breaks nothing), build
order is the explicit `order` array separate from the ids, and unknown record
keys are ignored at read time so receipts and project fields extend the
schema without code changes.

Two status layers. The worker-facing `status` runs
`backlog → ready-for-dev → in-progress → in-review → built → done`, plus
`cancelled`; `blocked` is an overlay object (type, reason, since, owner,
exact next action) that rides on top of any status instead of replacing it.
The board columns (`planned | ready | in-progress | review | built | done |
cancelled`) are derived at generation and never hand-written. Who writes
what — stated here only, enforced by `scripts/roadmap.py`:

| Transition | Written by | Rule |
| --- | --- | --- |
| `backlog → ready-for-dev` | orchestrator | plan approved and frontier verified |
| `ready-for-dev → in-progress` | worker | only after a successful `state.py` claim for the story id |
| `in-progress → in-review` | worker | with its receipts bound to the story HEAD |
| `in-review → built` | orchestrator | the premerge gate passed; every `after` provider is done (merge order is enforced even though review counts as met for starting) |
| `built → done` | orchestrator | merge landed; evidence bound to the merge SHA |
| set/clear `blocked` | worker (own story) or orchestrator | stored blockers are `human-decision`, `external`, `resource-contention` or `design`; dependency waiting is derived from `after`, never stored |
| `any → cancelled` | orchestrator proposes, human confirms | terminal; needs a recorded decision reference; a cancelled story still blocks its dependents until each is repointed |
| epic → `in-progress` / `awaiting-acceptance` | orchestrator | awaiting-acceptance only after every story is done or cancelled — closing children never closes the parent |
| epic → `done` / `parked` / `cancelled` | human | acceptance is the human checkpoint; parking carries a resume pointer; cancelling cancels the descendants |

Corollaries: no actor moves a story past `built` except the merge step; no
agent self-declares done; `done` and `cancelled` records are frozen — a
correction is a decision record or a new story, never a rewrite; review
findings append dated blocks to the record and never change status.

Readiness is computed from the dependency graph, never from list position or
titles: a story is ready when every `after` prerequisite is done or in
review, every epic gate it rides on is human-done, and it is unclaimed,
unblocked and not cancelled. The ready frontier is global across streams —
every unblocked, unclaimed candidate is offered, ordered inside an epic by
its `order` array. Generation also reports the cross-stream diagnostics (an
epic gate no story pins, a story waiting on an epic its own epic does not
declare, an order that contradicts a declared dependency), rejects cycles
loudly, reports degenerate records per story as problems instead of
crashing, and lists claim/record inconsistencies (in-progress with no live
claim, a claim with no record, claim paths outside the story scope) without
auto-repairing any of them.

Checkout and check-in are one protocol: the claim's task id is the story id.
Checkout = the frontier shows the story ready, then `state.py claim`, then
the worker writes `in-progress` on its own record. Check-in = result receipts
and `in-review` while the worker still holds its claim, then reconcile the
handoff and `state.py release`. Revision work reacquires ownership. The generator mirrors live
claims read-only into the projection; no board code ever writes claims or
the run state.

Regenerate the projections from this skill's directory:

```sh
python3 scripts/roadmap.py build --workspace "<project-root>"
```

During execution, refresh after meaningful worker steps, assignments, receipts
and blockers. With `manual` regeneration, run `build`; `on-write` updates also
build, but a claim-only change still needs a refresh. Reports link this snapshot
and state its generation time; unchanged inputs retain their earlier time.
The board shows recorded progress and [agent attribution](handoff.md#agent-attempt-receipts),
not live process telemetry. Check actual host handles before calling a worker
running; a claim, receipt or saved status alone does not establish liveness.
For a status-only query, read the existing snapshot and explain its age without
regenerating or dispatching. Continue authorized execution after progress
reports; route required decisions through [authority](authority.md).

`build` reads the records under the board lock and rewrites `roadmap.json`
and `dashboard.html` atomically; the revision counter and timestamp change
only when the inputs changed, so an unchanged board regenerates byte
identical, and deleting both artifacts rebuilds them in full from the
records. `roadmap.py derive --source <plan.json>` creates or refreshes
records from the planning source (joining by source key, never reusing ids,
never touching live fields). Derive fails closed on a stale counter: before
minting it checks that the `meta.json` counters exceed every existing record
id and collide with no record file, and refuses with a `board:` message and
zero writes otherwise — repair is an explicit edit of `meta.json` to above
the true maximum, then re-run derive; never an implicit overwrite. Adding a
story is therefore: extend the planning source, run derive, and only if it
refuses, repair the counters by hand first. `roadmap.py update` and
`roadmap.py epic` are the transition writes above. The board directory and the regeneration
policy (`on-write` or `manual`) are declared in `config.yaml` under `board`;
a malformed config fails closed.

## Helper limits

Atomic writes and a local lock protect the run files; the lock is not a Git
lock, a distributed fence, a task lease or an effect ledger. Helpers do not
infer intent, choose models or prove artifact truth — independent review still
reads and runs the evidence. Installation creates no run state.

## Bounds: claims, run.json and the run folder

Claims are a lease, not a ledger: release each claim when its work merges or
stops. The helper warns above 50 active claims and refuses new claims at 100
with an error naming the way out; `state.py reconcile` lists claims whose
worktree or HEAD no longer resolves (exit 1 when any are listed) so a human
can release them through the normal owner check. Claims are never expired
silently. A snapshot observes Git once per distinct worktree, never once per
claim, and no Git subprocess runs while the state lock is held.

`run.json` stays under 256 KiB: claim records are compact (owner, repo,
identity, paths, timestamps, a HEAD/dirty observation), released claims are
pruned from the active document, and only the last 16 releases are kept as
history — longer history belongs in the board record or the checkpoint.
Oversized or malformed state is refused whole, never partially read.

Program folder layout: `runs/<program>/` holds exactly `run.json`,
`CHECKPOINT.md`, `notes/`, `briefs/`, `evidence/`, `evals/` and `handoffs/`.
Receipts are small text files: nothing above 1 MiB (larger artifacts stay in
the consumer project or external storage and are linked by path), no binaries,
no symlinks, and at most 16 MiB across the run tree. Derived boards and status
summaries are not stored here — they are regenerable projections with no
canonical role. `state.py audit` reports usage against these budgets and
flags violations (exit 1) without altering any run artifact; the installer
keeps `runs/` out of version control while `config.yaml` and `context/` stay
tracked.
