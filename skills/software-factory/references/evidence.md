# Evidence and the gate

Phase: evidence — binding proof to a subject SHA before premerge and completion.

The evidence bar itself (what to run, who grades, what counts) lives in
[verification](verification.md). This reference covers the manifest that binds
that evidence to one subject, and the helper that checks its structure.

## The rule

Every piece of proof binds to a subject SHA — the full 40-hex commit the proof
ran against. Story checks bind to the story HEAD; integration checks bind to the
merge SHA; deploy proof binds to the deployed SHA. Proof about a different SHA
than the one being merged is not proof of this change.

## The manifest

Before a gate, write an evidence manifest (JSON) into the run's evidence
directory:

- `subject_sha` — full 40-hex SHA every check binds to.
- `author` and `reviewer` — distinct; self-approval is a structural failure.
- `checks` — keyed by check name. Default required names: `tests`, `eval`,
  `review` and `ci` at the `premerge` phase; `complete` adds `deploy`. The
  required names come from the project's configuration
  (`verification.required_checks`), so a project can rename or extend the set.

Each passing check carries its matching `subject_sha`, a relative artifact path
inside the evidence root, and — where the check ran a command — the command and
the integer exit code `0`. A `deploy` check also carries `deployed_sha` equal to
the subject. A check that genuinely does not apply uses
`status: not_applicable` with a matching `subject_sha`, an `approved_by`, a
`reason` and a `decision_ref` pointing at the scoped approval.

`fail`, `skipped`, `unknown` and `infra_error` never pass, whatever the artifact
says. Missing proof is blocked, not passed.

## The gate helper

Run from this skill's directory:

```sh
python3 scripts/gate.py --report "<project-root>/.software-factory/runs/<program>/evidence/<manifest>.json" \
  --root "<project-root>/.software-factory/runs/<program>/evidence" \
  --sha "<full-subject-SHA>" --phase premerge
```

Use `--phase complete` after integration and deploy proof. The helper checks
structure only: SHA match, author/reviewer independence, required checks for the
phase, pass-status rules, integer exit codes, artifact existence inside the
evidence root and deploy-SHA freshness. It reads data and never executes
anything in the manifest.

**The gate does not prove the artifacts are true.** The independent reviewer
still reads the diff and runs or inspects the evidence; the gate exists so that
stale, mismatched or self-approved evidence cannot slip through unnoticed.

## Protected board transitions

New `built` and `done` transitions call the strict gate in `gate.py`; an actor
label alone cannot advance them. Historical version-1 terminal records remain
readable and frozen without migration or invented proof.

The worker submits `in-review` while still holding the claim. Use `--sha` with
the full current review commit when receipts contain several subjects. The
board records `review_subject_sha`; a new `built` must match it. Full SHA
syntax and recorded subject equality are checked, not Git commit existence or
the truth of the worker's observation. The independent reviewer reconciles
the actual diff and commit before acceptance.

For either protected transition pass `--sha <full-subject>` and
`--evidence <workspace-relative-manifest.json>`. Artifact and decision paths
inside these board manifests are **workspace-relative** (the standalone gate
CLI continues to use its explicit `--root`). Every passing check needs an
`artifact_sha256` matching the current bytes. Reads are limited to 1 MiB per
file, refuse symlinks at every component and never execute manifest commands.
New strict reads reject duplicate JSON keys and non-finite numbers; each
gate accepts at most 64 required checks and reads at most 8 MiB of check
artifacts in aggregate. JSON receipts (by case-insensitive suffix or
JSON-looking content) with subject/verdict/self-hash fields must reproduce
those claims; unknown subjects, non-pass verdicts and any declared status
other than `pass` fail. Partial-case success is not full gate proof. BOM and
UTF-16/32 structured evidence must be normalized to UTF-8 without a BOM
before submission; changing a filename or encoding cannot hide a failed receipt. Required check names
still come from the existing `verification.required_checks` list. A required
review check is named `review` or carries `kind: review`; author and reviewer
are nonempty distinct identities, and author matches the implementation owner.
These labels are structural assertions, not authenticated identities.

`built` still requires every provider done and every applicable epic gate
accepted; readiness continues to count in-review providers as met. It stores
the manifest path, SHA-256, subject, identities and check bindings under
`accepted_gates.premerge`. `done` consumes the complete-phase gate for the
merge SHA, rechecks the accepted premerge manifest/artifacts, and requires:

- `candidate_sha` equal to the accepted premerge subject;
- `integration` with `status: pass`, that `candidate_sha` and merge `subject_sha`;
- the `deploy` check's matching `deployed_sha`, plus nonempty `artifact_id`
  and `environment` identifying the observed effect or approved local staging.

Completion retains every previously accepted premerge check obligation and
adds current configured requirements. Weakening the configuration cannot
remove old proof from revalidation. Protected transitions read configuration
once through the same bounded, no-follow reader; graph queries retain their
captured-source configuration contract.

Completion requires a passing effect check, rather than an applicability
exclusion standing in for effect proof.

This establishes recorded provenance, not a remote merge or deployment fact.
An unknown external outcome must be reconciled before writing a pass report.

## Required checkpoint decisions and exceptions

`plan_checkpoint` requires a decision before ready-for-dev and premerge;
`hitl` or `done_checkpoint` requires one before completion. Supply
`--decision <workspace-relative-decision.json>` once. The board saves its
digest and reuses a still-valid scoped decision; superseded references remain
in `checkpoint_history`. No repeated interview is needed for the same scope.

The JSON decision has `decision: approve`, `scope: {story: <integer>}`,
`phase: plan|complete`, nonempty `approved_by`, timezone-aware `approved_at`,
and either the matching full `subject_sha` or `scope_sha256`. The latter is
`roadmap.scope_digest(record)`: SHA-256 of compact sorted JSON over id, epic,
source_key, title, type, after, covers, scope, risk and the three checkpoint
flags. If both subject and scope are supplied, both must match. Its `source`
contains `kind: user-conversation|approval-surface`, a nonempty trusted-source
`ref`, a contained nonempty `artifact`, and that artifact's `sha256`. The host
must reconcile this reference with the trusted owner conversation; a local
file and `--actor human` do not authenticate approval. Missing, revoked,
changed or out-of-scope decisions block the transition with no story or
projection write. Governing policy and final publication authority stay separate.

A `not_applicable` check additionally carries `decision_sha256` for its
`decision_ref`; the scoped decision's phase is `exception:<check-name>`.
Independent review cannot be excluded, and a failed verdict cannot be
relabeled as an applicability exception. An eval receipt whose override
changes a non-pass verdict needs an explicit `disposition: approved_override`
and `override_decision_ref`/`override_decision_sha256`, phase
`override:<check-name>`. That decision also names the exact receipt
`artifact_sha256`. Original receipt bytes and verdict history remain
the evidence; the disposition is saved explicitly rather than hidden as an
ordinary passing result.

On revision the worker must hold or regain the claim, return in-review/built
work to in-progress, and submit a fresh review subject. Existing receipts and
prior gate bindings in `gate_history` remain; affected evidence must be
refreshed. Use immutable, attempt-specific artifact paths to keep prior proof
inspectable. Failed gates leave the story and generated projections unchanged.

## Epic acceptance and preserved history

New human epic acceptance rechecks current child closure, exact explicit
child membership/order, accepted providers, protected child gates and required
checkpoint references. It binds the declared epic outcome and exact current
child/provider record bytes with `roadmap.epic_review_scope(...)`. Scope reads
are bounded to 8 MiB in aggregate; an epic review admits at most 256
children and 256 provider references. Merely reaching
`awaiting-acceptance` does not authorize closure after descendants change.

Supply `--decision <workspace-relative-decision.json>` to human epic `done`.
The source-linked decision uses `scope: {epic: <integer>}`, `phase: epic`, the
matching `scope_sha256`, and an `evidence` binding with `artifact` and `sha256`.
That contained independent reconciliation bundle has `status: pass`, the same
`scope_sha256`, distinct nonempty `author`/`reviewer` identities and exact
`legacy_children`. The reviewer cannot own a reviewed child implementation. Optional `artifacts` are contained digest bindings, at most
64, totaling at most 8 MiB including the bundle. If `--evidence` is supplied,
it must identify the very bundle the owner approved. Replaced acceptance
references remain in `acceptance_history`.

Historical done children need no synthetic gate backfill. The new decision
and independently reviewed bundle must explicitly list their IDs in
`legacy_children`, with the bundle bound to the exact reviewed scope. This
is reconciliation evidence for owner review, not a claim that old external
effects became kernel-verified. Newly created or reviewed stories carry
`evidence_contract: 1` and cannot use this historical reconciliation route
to omit their required gates. Cancelled children are included in the reviewed
scope without implying implementation or deployment.

Derivation also respects frozen terminal stories and epics: unchanged source
preserves terminal source bytes, but changed terminal fields, child additions/order or stream
membership are refused before publishing any records or projections. Route
changed accepted scope to new work and an explicit decision. Historical
terminal records remain readable without a schema/version migration.
