# Receipts: the evidence contract

Every run writes receipts to the run's neutral path,
`<receipts_dir>/<run-id>/evals/`:

```text
receipt.json          # the run receipt
cases/<CASE-ID>.json  # one per case: status, expected vs actual, ...
artifacts/<CASE-ID>/  # failure artifacts only
```

Receipts are text artifacts — per-case JSON plus small, bounded failure
artifacts (output tails, HTTP dumps, unified diffs, harness logs). A
browser harness's screenshots or traces are referenced by path, never
copied in: no binaries under the state root.

## The run receipt

Fields: `run_id` (`r-<UTC timestamp>-<mode>`), `mode`, the covered
`story_ids`/`epic_ids`, `started`/`finished`, `git_sha`, `config_sha256`
(the plan digest), the exact `command`, the per-case `cases` results, the
`skipped` set with reasons, `totals`, the `verdict`
(`pass | fail | unverified`), `overrides`, and `self_sha256`.

The self-hash is the sha256 of the receipt serialized as UTF-8 JSON with
sorted keys and compact separators, the `self_sha256` field excluded — so
removing the field and re-digesting reproduces the stored value.
`sf_eval.py verify --receipt` does exactly this and also requires the
verdict to be `pass`; a tampered or non-green receipt exits nonzero with
the reason.

## Failure receipts

A failing case additionally records its Given/When/Then criterion, the
expected and actual values, the grader output, the artifact paths, exit
codes and output tails, and a `triage_hint` with a `suspect_eval` flag set
when repeated failures (at or beyond the retry cap) look like a broken
case. The loop reads the receipt, not the transcript.

## Manifest citation

The gate and verification manifests carry an `eval` block (canonical
location `checks.eval`) citing the run id, the verdict, the per-case
results for the covered stories, the receipt path and the receipt's
`self_sha256`. `sf_eval.py verify-manifest --manifest M --root R` refuses —
nonzero, with a named reason — a manifest whose `eval` block is missing,
whose cited receipt does not exist, whose digest does not verify, or whose
receipt verdict is not `pass`. The `not_applicable` path requires the
approved override record (who, when, why) rather than counting a skip as a
pass.

## Overrides

`sf_eval.py override --receipt R --who W --reason TEXT` appends the record
(who/when/why) to the receipt's `overrides` and re-hashes it; the manifest
then cites the new digest. An override is honest evidence on record; a
silently skipped gate is not.
