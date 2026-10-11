# Eval-first setup

Run setup after stories are drafted and before any story enters the
engineering queue. The plan is drafted **with** the user, not for them: the
skill asks rather than guesses, and the user signs off. A story is not
implementable until its cases exist and are approved — the orchestrator
never dispatches a story without approved cases.

## Per-surface suites

Enumerate every surface the work touches; each gets its own suite with a
declarative harness declaration, and each surface declares its adapter. One
acceptance criterion can produce one case per surface — a shopping site's
"add to cart" yields a frontend case AND a backend case (worked example
below). The standard set is extensible: add a surface with its own id, kind
and adapter.

| Surface id | Kind | Typical harness (declared, swappable) | Case style |
| --- | --- | --- | --- |
| `frontend` | web-ui | host browser driver, Playwright, or fetch for server-rendered pages | user-visible behavior assertions, auto-retrying |
| `backend` | http-api | stdlib HTTP probe or the project's own test command | status/body/schema/state assertions per endpoint |
| `data` | pipeline | golden-file diff, query or test command | schema/freshness/reconciliation gates per stage |
| `behavior` | agent-llm | judge harness the host provides | outcome checks first; rubric cases only where subjective |
| `ops` | deploy | HTTP probe against the deployed URL | post-deploy canary: service up, critical-path smoke |

## From criterion to case

Each acceptance criterion becomes one or more cases in Given/When/Then form
with concrete example data: exact SKUs, exact messages, exact thresholds. A
criterion that cannot be made unambiguous — no concrete data, no exact
message, no threshold — is disambiguated with the user, and the answers are
recorded on the case. Never guess an ambiguous criterion into a case.

## The sign-off gate

The plan carries a `signoff` block recording who approved, when, and the
plan digest (`plan_sha256`). Until the cases are approved, the story stays
out of the queue. A criterion change — including an eval-fix that changes a
criterion — re-opens sign-off for the affected case only, not the plan.

## Risk tiers scale the floor, never remove it

| | Tier 0 (tiny/greenfield) | Tier 1 (small, real users) | Tier 2 (production, money, auth, data) |
| --- | --- | --- | --- |
| Per criterion | ≥1 deterministic `fail_to_pass` case | + a negative case per behavior | + contract cases per consumer, state checks on write paths |
| Smoke | ≥1 critical-path case per surface | + one per public entry point | + auth/error-path smoke |
| Regression | ≥3 cases per epic at close | all prior epic cases | + data quality gates |
| Nondeterminism | none — deterministic only | rerun-on-fail | `pass^k` on premerge |
| Judge cases | none | allowed, calibrated, never sole gate | + human spot-check cadence |

## The eval config section

The plan lives at the configured plan file (default
`evals/eval.config.json`, holding the `eval` section values of the project
config). The section is strict — `schemas/config.schema.json` rejects
unknown keys and unknown grade or harness types — with keys:

- `version`, `plan_file`, `receipts_dir`, `user_signoff_required`,
  `risk_tier`, and `signoff` (status, approved_by, approved_at,
  plan_sha256);
- `minimums`: cases per criterion, negative cases per behavior, smoke paths
  per surface, regression cases per epic, and the tier below which only
  deterministic grades are allowed;
- `surfaces`: id, kind, `base_url_env`, a `harness` object whose `type` is
  a closed enum (`command | http | file_state | golden | browser | judge`)
  with an optional `run` command and `report` format, and the suites;
- `cases`: the case contract — [cases](cases.md);
- `modes`, `routing`, `receipts`, `judge_policy` — [modes](modes.md) and
  [receipts](receipts.md).

## Worked example

[examples/eval.config.example.json](../examples/eval.config.example.json)
is a complete tier-1 plan for a small shopping site. Story S-12 ("add
product to cart") is proven on two surfaces:

| Criterion | Cases |
| --- | --- |
| AC1: add an in-stock product | `FE-CART-001` (frontend click-through), `BE-CART-001` (POST + GET), `BE-CART-003` (cart state) |
| AC2: out-of-stock rejected (negative) | `FE-CART-002` (button disabled), `BE-CART-002` (409 `out_of_stock`) |
| AC3: cart persists across reloads | `FE-CART-003` |

E-1's `FE-PDP-001` rides along as `pass_to_pass` regression, `FE-HOME-001`
is the smoke case, `BEH-CHECKOUT-001` shows a fully marked judge case, and
`OPS-HEALTH-001` is the canary probe.
