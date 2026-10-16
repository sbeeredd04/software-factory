# Reviewed deterministic overlays

The user owns `.software-factory/overlays/<id>/manifest.json`, payload and retained
evidence. Register its exact manifest SHA-256 in the existing config. The schema
is `schemas/overlay.schema.json` in the source pack and `sf-evolve/schemas/` in
installed/native skill layouts. The helper uses only the shipped offline schema.

## Proposal and evidence bindings

The manifest requires `version: 1`, slug `id`, `target`, `base_sha256`, `mode`
(`append` or `replace`), `payload: {path, sha256}`, nonempty `evidence` references,
`author` and `risk` (`routine` or `material`). Payload is a separate bounded file
inside the overlay directory. All paths are contained, canonical, nonsymlink
regular files. Reads are bounded to one MiB, with a finite source-file budget.

`subject_sha256` hashes the JSON object containing exactly those nine fields in
that order-independent representation: Python `json.dumps(..., sort_keys=True,
indent=2, ensure_ascii=True) + '\n'`, UTF-8. The read-only helper's `subject`
function implements it. Review and approval are outside the subject to avoid
self-referential hashes; their references bind their exact artifact bytes.

Add these required records, each carrying the same `subject_sha256`:

- `review`: `by`, `verdict: approved`, and `artifact: {path, sha256}`. The JSON
  artifact must itself carry the matching subject, by and verdict. Reviewer
  identity must differ from the author; the host verifies actual independence.
- `regression` and `canary`: `result: pass` and `artifact: {path, sha256}`. Each
  JSON artifact carries the matching subject and result, with actual case/output
  evidence. A label alone is insufficient for the host's evidence review.
- `approval`: `by`, `kind: standing-go|human`, `decision: {path, sha256}`.
  Material changes require `human`. The host reconciles that source with actual
  current authority; structural validation never authenticates the decision.

Evidence cannot be the target, manifest or payload itself. Keep original failed
runs alongside later proof. Reusing another subject's review or changing any
bound artifact makes composition fail before target writes.

## Supported composition and conflicts

Targets are existing generated canonical skill `SKILL.md` or one-level Markdown
`references/*.md` under `.claude/skills/` or `.agents/skills/`. The orchestrator
`software-factory` skill, scripts, agent role files, BMad bodies, TOML, host hooks,
permission files and arbitrary user files are outside this implementation.
Configured governing documents and decision stores are protected even if they
alias an otherwise eligible target. Replacement preserves exact generated entry
frontmatter, including host policy, identity and invocation fields.

`append` means base bytes followed by payload bytes, with no automatic newline.
`replace` means the reviewed full bytes. The generated upstream must match the
recorded base SHA-256. The installer composes before planning, owns the final
hash, checks captured sources and upstream under its lock, and rechecks before
publishing its existing ownership manifest. It refuses edited current targets
even with `--allow-overwrite`; the user must reconcile them explicitly.

No-config installation has zero overlays. Registered malformed/missing inputs
fail before mutation. Repeat identical installation produces identical bytes;
append does not accumulate. There is one supported overlay per target. Selecting
a host that cannot project a registered target fails explicitly; select the
required hosts or make a reviewed registry change.

```sh
python3 skills/sf-evolve/scripts/evolve.py propose --root <project> --manifest .software-factory/overlays/example/manifest.json --base evidence/generated-base.md
python3 install.py install --project <project> --host all --skip-bmad --dry-run
```

The first command requires a separately captured exact generated base. A drift
returns a conflict and comparison toward a possible rebased candidate, never an
applied patch. Preserve the old manifest/evidence; a rebase needs a new subject,
review, canary and source decision. Never replace the base hash just to pass.
After host GO reconciliation, the ordinary installer applies the reviewed plan.
Native plugin generation remains independent of consumer config and overlays.

## Rollback and removal

An interrupted transaction restores only unchanged transaction-owned bytes and
preserves concurrent edits. The original user restoration basis remains in the
existing installation manifest across updates. Uninstall recognizes the same
projector destinations and leaves registry, overlay sources and evidence alone.

A later behavioral rollback is another bounded authorized proposal: restore a
previous reviewed payload, or explicitly remove the overlay registration and
reinstall the canonical base. Inspect the resulting ownership and affected
behavior. Neither option erases failed evidence or edits unrelated customizations.
