# Eval policy — Software Factory

The method owner is the `sf-eval` skill (`skills/sf-eval/`); this module
states how this repository applies it.

- **Eval-first.** No story is done without its cases green or an approved
  override on record. The pack's own suite is `evals/eval.config.json`;
  it was drafted with the user and carries the sign-off block.
- **Per-surface suites.** The pack's surfaces are the kernel helpers, the
  validation tooling and the skill content; each surface's cases live in
  the one plan, linked to board stories.
- **Deterministic-first grading.** Cases grade at the lowest rung that can
  decide them: state, command, http, browser, golden, then judge. The
  pack's suite is fully deterministic and offline; it uses no judge cases
  and no live model or agent CLI anywhere.
- **Judge rules.** Where a future case is genuinely subjective, it follows
  the skill's judge rung: binary assertions, one dimension, an "Unknown"
  escape, a reference example, calibration, marked nondeterministic with
  trials and a consistency policy, never the sole gate below the top tier.
- **Overrides.** A human override is recorded on the receipt (who, when,
  why) and re-hashes it; a silently skipped or fabricated receipt violates
  the pack's no-fabricated-proof boundary.
- **The gate runs the evals.** `scripts/check_all.sh` runs the suite in
  `premerge` mode and fails on a red verdict; receipts land under the
  run's neutral path and are citable by gate manifests.
