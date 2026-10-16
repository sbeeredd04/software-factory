# 0025 — Pin compatible BMad external modules

Status: accepted · 2026-10-15

## Context

BMad 6.12.0's original command fails with the newer TEA module format.
Guarded temporary installs succeeded with compatible external module tags.
The owner answered: "Approve all three tested pins (recommended)."

## Drivers

Reproducible module selection, compatible provisioning and preserved existing work.

## Options

Defer provisioning; pin TEA alone; or pin all three tested external modules.

## Outcome

Keep BMad Method 6.12.0 and append explicit installer arguments:
`--pin tea=v1.27.2 --pin bmb=v2.2.2 --pin cis=v0.3.2`.
Existing and partial BMad installations retain their conservative reuse policy.
This authorizes the command amendment, without enabling automatic updates.

## Consequences

- Record observed installed versions, channels and upstream source identities.
- Tags and npm dependencies are not an immutable cryptographic lock.
- Native planning remains available; no BMad files are vendored.
- Original failures and exploratory evidence remain inspectable.

## Confirmation

Story 23 must prove the amended command through the actual installer,
with guarded disposable consumers, regression checks and independent review.
The owner decision does not itself establish successful installation or acceptance.
