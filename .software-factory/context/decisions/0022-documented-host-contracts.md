# 0022 — Documented invocation controls and honest permission claims

Status: accepted · 2026-10-15

## Context

Recovered host requirements conflicted with current official host contracts.
The owner directed completion of a robust portable pack across all three hosts.

## Drivers

- Explicit invocation must use each host's documented control.
- Permission reports must describe actual enforcement capabilities.

## Options

- Retain recovered fields and claim behavior the host does not guarantee.
- Correct projections against official contracts and expose unverified loading.

## Outcome

Generated shared skills carry Cursor's explicit-invocation field when Cursor
is installed and Codex's openai.yaml policy when Codex is installed. Canonical
frontmatter stays standard. Codex agents omit ineffective sandbox_mode and
fixed models; parent permissions and actual restrictions govern execution.

## Consequences

- Sequential additions preserve both hosts' policies and ownership metadata.
- Combined loading and actual host behavior remain explicitly unverified.
- Required enforced read-only access needs an observed supported restriction.
- No parent permission, trust or home configuration is changed automatically.

## Confirmation

- Official source links and acceptance checks: docs/plans/host-contract-correction.md.
- Independent source review of host corrections; 50 host and 20 installer tests passed.
- Full static gate at 9b849e7: 432 unit tests, 30 evals, all steps passed.
