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
