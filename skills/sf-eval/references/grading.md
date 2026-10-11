# Grading: the deterministic-first ladder

Grade every case at the lowest rung that can decide it. The order is fixed
and the `grade.type` enum is closed — `state | command | http | browser |
golden | judge` — so receipts and gate logic stay uniform across harnesses.
Grade outcomes, not paths: assert what the work produced (the row exists,
the order is placed, the file is written), never the step sequence an agent
took to produce it.

1. **state** — assert the end state directly: file exists, JSON field
   equals, content marker present.
2. **command** — run a declared command (the project's own tests, a
   linter); assert the exit code plus an optional output pattern.
3. **http** — probe a declared local URL: status, body field, header or a
   JSON-schema-subset assertion (contract by example).
4. **browser** — a user-visible, auto-retrying assertion on rendered output
   (visible text, role/text locators, click-through); capture evidence on
   failure only, so the green path stays fast.
5. **golden** — diff produced output against an approved golden under
   version control; the diff is a reviewed artifact.
6. **judge** — the marked last resort, for genuinely subjective criteria
   only. Rules below.

The runner (`../scripts/sf_eval.py`) executes the deterministic rungs
natively. `browser` and `judge` run through the harness command the surface
declares; a missing harness makes the case `unverified`, never a pass. The
runner itself calls no model — a judge grade is a declared command or
rubric the host environment provides.

## The judge rung (marked last resort)

- Pass/fail assertions, never free-form numeric scores; one rubric
  dimension per judge call.
- An explicit "Unknown" escape so the judge can abstain.
- A full-mark reference example attached to the case, with calibration
  samples stored alongside it.
- Calibration before trust: run the known-good and known-bad canaries
  before accepting any judge's grades — a judge that passes a known-bad
  case is unusable, and an uncalibrated rubric is reported as such rather
  than trusted.
- Grading is done by a fresh, best-fit evaluator over redacted traces and
  receipts, and judge grades stay subordinate to effect tests: an effect
  failure fails the case regardless of the judge's grade.
- Every judge case is marked `nondeterministic: true` in the plan, with a
  declared trial count and a consistency policy: `pass@k` where one success
  suffices, `pass^k` for release consistency, `majority` for a vote; keep k
  small (1–3).
- A judge case is never the sole gate for a story below the top risk tier —
  pair it with at least one deterministic case.
