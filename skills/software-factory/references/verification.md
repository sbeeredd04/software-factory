# Verification and the evidence bar

Phase: verification — proving a story on its actual HEAD before integration.

Never grade a worker's report alone. Inspect the actual diff, the actual test
output, the persisted effects and the delivered experience. The author cannot
approve its own work.

## Evidence ladder

1. **Deterministic tests first:** contracts, effects, isolation, idempotency,
   concurrency, cancellation, partial and unknown outcomes, failure and restart,
   compatibility.
2. **Project evals:** reuse the project's own eval runner and acceptance slice.
   Pin source, model and rubric versions; capture scenario IDs, commands, exit
   codes and evidence paths. The [`sf-eval`](../../sf-eval/SKILL.md) skill owns
   the eval gate: per-surface suites, per-story `fail_to_pass` and
   `pass_to_pass` cases with stable IDs, deterministic-first grading and
   cost-tiered runs. Eval receipts carry a sha256 self-hash and are cited by
   gate manifests; a story does not pass without its evals or an approved
   override record.
3. **Actual effects:** verify effects in real state — files, database rows,
   provider dashboards, queues — not in promising prose. An effect failure fails
   the scenario regardless of any qualitative grade.
4. **Qualitative eval:** subjective criteria follow the judge rung of the
   [sf-eval grading ladder](../../sf-eval/references/grading.md); judge
   grades stay subordinate to effect tests.
5. **Independent review:** a non-author reads the actual diff with the plan and
   the failure/effect evidence, and confirms findings by reproducing them.

The eval gate applies on both loops: a bug fix verifies against the story's
eval cases just as a feature does, with the confirmed reproduction captured as
a `fail_to_pass` case before the fix is accepted. An eval failure is a finding
that routes back into the owning loop; it is never waived silently — only an
approved override record excuses it.

Apply `sf-design` and its focused skills (`sf-smell-audit`, `sf-refactor`,
`sf-patterns`) again at diff review, holding the anti-bloat bar: reuse first,
the smallest complete diff, no unrequested abstraction, obsolete-path deletion
as part of done, and one runnable check per story.

## Output statuses

Per criterion: `pass`, `fail`, `infra_error`, `unknown` or `not_applicable`.
Attach concise evidence quotes or receipt references, the observed effects, the
subject SHA and the reason for any escalation. `not_applicable` requires a
scoped, approved rationale on record. Skipped checks and infra errors never
count as passes; a known-defect expected failure stays a failure until the
required slice is green.

Missing or unreadable proof is a blocked acceptance, never a pass. A worker's
prose summary cannot substitute for the diff, the command output or the effect
evidence.

## Freshness and scope

Run a story's checks on its HEAD. Independent stories can be verified
concurrently; serialize only the phase-scoped shared resource a check actually
uses. After a dependent merge or rebase, rerun checks for the affected stories
only and leave unaffected workers on their existing base. Required CI and eval
evidence bind to the integration or merge SHA, and deploy proof binds to the
deployed SHA.

Do not confuse a mocked eval with a staging run, a health-check 200 with
functional proof, or a dry run with a live pass.

Give a short verdict in chat. Keep detailed evidence in the run's evidence
directory, linked from receipts — never save raw credentials, authenticated
transcripts or private reasoning.

The structural gate that binds this evidence to a subject SHA is described in
[evidence](evidence.md).
