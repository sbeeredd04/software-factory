---
name: sf-eval
description: "Makes evals a precondition of work: per-surface suites signed off before stories queue, per-story fail_to_pass/pass_to_pass cases with stable IDs, deterministic-first grading, cost-tiered runs, sha256 receipts. Use for eval setup, story evaluation or failure triage."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: evaluation
  release: v0.1
---

# sf-eval

Evals are a precondition of work, not an afterthought: no story enters the
engineering queue until its eval cases exist and the user has signed off,
and no story is done until its cases are green or an approved override is
on record. This skill owns the eval method — eval-first setup with
per-surface suites, the per-story case contract, the deterministic-first
grading ladder, the cost-tiered run modes and their gate mapping, failure
routing, and the receipts contract. The evidence gate consumes the
receipts; its rules stay in [verification](../software-factory/references/verification.md).

## Map

- [Setup](references/setup.md) — per-surface suites drafted with the user,
  disambiguation instead of guesses, the sign-off gate, risk-tier floors,
  the eval config section, the worked example.
- [Cases](references/cases.md) — `fail_to_pass` + `pass_to_pass` cases with
  stable story-linked IDs, balanced sets, satisfiability.
- [Grading](references/grading.md) — the six-rung deterministic-first
  ladder and the marked, calibrated, never-sole-gate judge rung.
- [Modes](references/modes.md) — quick / epic / premerge / canary, the gate
  mapping, and failure routing: triage, quarantine, retry caps, overrides.
- [Receipts](references/receipts.md) — per-run and per-case receipts,
  failure artifacts, the sha256 self-hash, manifest citation.

## The runner

`scripts/sf_eval.py` is the standard-library eval runner: it executes the
deterministic rungs natively (`state`, `command`, `http`, `golden`), shells
out only to a harness the plan declares (`browser`, `judge`), works
offline, never calls a model and installs nothing. A missing harness is
`unverified`, never a pass. Run it from the consumer repository root
(`<skill-dir>` is the installed skill directory):

    python3 <skill-dir>/scripts/sf_eval.py run --plan evals/eval.config.json --mode quick --story S-12

`verify --receipt` re-checks a receipt's self-hash and verdict;
`verify-manifest` checks a gate manifest's eval citation; `override`
records who/when/why on a digest-valid receipt (a tampered one is
refused) and transitions its verdict so the manifest can cite the new
digest. `--help` lists every option. A worked plan ships at
[examples/eval.config.example.json](examples/eval.config.example.json).
