# Run modes, gate mapping and failure routing

Four cost-tiered modes; every run writes receipts (see
[receipts](receipts.md)).

| Mode | Scope | Budget | Gates |
| --- | --- | --- | --- |
| `quick` | the story's cases on all its surfaces + the surface smoke set + the story's `pass_to_pass` cases | seconds to minutes; deterministic rungs only | story done |
| `epic` | all the epic's cases on all surfaces + the full regression suite | minutes | the epic's policy-selected acceptance and verification manifest |
| `premerge` | every case in the plan, with trials for the nondeterministic ones | as long as needed; may run in CI | the gated merge; rerun as deploy-proof input |
| `canary` | the smoke set + ops probes against the deployed URL | seconds | the deploy proof |

## Wiring to the factory gates

The modes and their gate mapping are declared in configuration — `modes`,
plus the claims listed in `receipts.manifest_citation.required_for`. The
gate check names stay configurable: they ride `verification.required_checks`
in the project config, and the gate helper's built-in defaults already name
`eval`; nothing eval-specific is hardcoded into the gate. The feature and
bug workflows name the eval gate as a verification stage: a story-done
claim without a green receipt citing its case IDs fails the evidence gate,
a merge manifest without a green `premerge` run fails, and a deploy proof
without a `canary` run fails.

## The iterate loop

`quick` runs inside the implement/verify loop on every iteration: run, read
the receipts, then finish green or triage, fix and rerun. A failing case
attaches to the story's work item; failures iterate before any gate, not
after one.

## Failure routing

- **Failure receipt.** A failing case writes what the loop needs:
  criterion, expected vs actual, grader output, artifacts, exit codes and a
  triage hint (fields: [receipts](receipts.md)).
- **Triage is binary.** Code-fix — the implementation is wrong — or
  eval-fix — the case is impossible, unfair or ambiguous. An eval-fix that
  changes a criterion re-opens sign-off for that case (see
  [setup](setup.md)). A case that keeps failing across attempts and trials
  is flagged `suspect_eval` in its receipt and escalated to the user rather
  than retried forever.
- **Quarantine.** A case that flips pass/fail with no change is marked
  `quarantined`: excluded from blocking, tracked as eval debt in the plan,
  and de-flaked or downgraded before the next epic closes.
- **Retry cap.** The quick loop caps fix iterations per case (default 3,
  `routing.retry_cap_per_case`); reaching the cap escalates — risk routing
  and/or the human checkpoint — instead of looping forever.
- **Graduation.** When an epic closes, its `fail_to_pass` cases graduate
  into the regression suite and become `pass_to_pass` for everything after;
  new production failures become new cases.
- **Recorded overrides.** A human may override a failing gate only as a
  recorded override — who, when, why — inside the receipt
  (`sf_eval.py override`). Fabricating, omitting or silently skipping a
  receipt violates the pack's no-fabricated-proof boundary.
- **Trust gradient.** The loop starts reviewed — the agent iterates on
  evals and a human approves the diffs — and deepens automation only as the
  gate proves itself.


Apply [authority](../../software-factory/references/authority.md) throughout the
loop. Routine case refinement may use a real scoped owner delegation; material
success changes, weakened cases or unapproved applicability still need the required
owner decision. Preserve failed history and the independent proof floor.
