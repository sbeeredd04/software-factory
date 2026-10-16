# Handoffs: worker briefs and returns

Phase: handoff — every dispatch and every return, in a shape that survives
interruption.

Adapt the fields to the task; these are contracts for evidence, not a parser.
Keep large sources linked and recoverable rather than inlined.

## The brief (orchestrator to worker)

```text
Role/objective: <bounded job>; story/AC IDs: <...>; authorizing GO: <ref>.
Sources: <principles sections, decisions, actual code anchors and their freshness>.
Repo/remote: <absolute root + identity>; worktree/branch/base SHA: <exact values>.
Exclusive writes: <claimed paths>; dependency unlock proof: <receipts>.
Phase resources: <owner/phase for any shared resource>; scheduling rationale: <one line>.
Contracts/design/deletions/compatibility: <decisions>; risks: <...>.
Authority: <delegated actions within scope; the entry's hard boundaries apply>.
Verify: <commands, AC and effect assertions, eval slice, deploy proof, failure cases>.
Return: the contract below.
```

## The return (worker to orchestrator)

```text
HEAD/diff: <actual HEAD SHA, diff or changed paths — not a summary of them>.
Commands: <commands run with their real exit codes>; artifacts: <paths/links>.
Evidence: <per-AC results and verified effects; what was observed, where>.
Uncertainty: <what is unknown, unverified or flaky>.
Next: <one exact next action>; blockers: <...>.
```

## Agent-attempt receipts

For durable attribution, use the existing story `receipts` extension rather
than a separate status store. The required `subject_sha` is the actual baseline
at dispatch or the actual result SHA for a return. Optional fields are:

```text
type: "agent-attempt"; agent: <host agent/session identifier>; role: <role>;
skill: <skill used>; requested_model: <requested route>;
effective_model: <observed model or null>; phase: <phase>; status: <status>;
recorded_at: <timestamp>; summary: <short factual report and route rationale>.
```

Use phases `dispatch | implementation | verification | review | recovery` and
statuses `assigned | reported-complete | failed | cancelled | awaiting-review`.
Absent or null `effective_model` means unknown; never infer it from the request.
These are optional descriptive receipt fields, not new story transitions or a
kernel-validated schema. A receipt records a report, not proof that a process
is live, an effect occurred or independent verification passed. Link the
actual evidence separately and use distinct receipt names for separate attempts.

Attach a JSON receipt from this skill's directory, using the existing writer
authority (worker updates require its live claim):

```sh
python3 scripts/roadmap.py update --workspace "<project-root>" --story <id> \
  --actor worker --owner <owner> --receipt attempt-1=<receipt.json>
```

At check-in, submit result receipts and `in-review` while the claim still
exists; reconcile the handoff before releasing it. Later revisions reacquire
ownership. A dispatch receipt does not substitute for result evidence.

## The rules of the contract

- Workers get the exact orchestrator-created worktree, absolute edit paths and
  an explicit working directory — they do not pick their own location.
- Workers return facts: actual SHAs, diffs, exit codes and artifact references.
  The orchestrator and independent reviewers inspect those, not the prose.
- Unresolved scope or contract questions escalate back to the orchestrator; the
  worker does not expand scope, publish or merge on its own.
- No worker approves its own work. Acceptance is independent and stays with the
  orchestrator.
- Durable, factual handoffs — never raw credentials, authenticated transcripts
  or private reasoning — are what make [recovery](recovery.md) possible.
