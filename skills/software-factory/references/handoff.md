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
