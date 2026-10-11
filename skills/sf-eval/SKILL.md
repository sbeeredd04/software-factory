---
name: sf-eval
description: "Makes evals first-class. Sets up per-surface eval suites (e.g. frontend and backend) with user sign-off before stories queue, gives every story fail-to-pass and pass-to-pass cases with stable IDs, and runs cost-tiered evals with sha256-receipted evidence. Use for eval setup and story evaluation."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: evaluation
  release: v0.1
---

# sf-eval (placeholder)

> **Placeholder — this is not the shipped skill.** This file exists so the
> eleven-skill layout validates. The full eval skill (per-surface suite setup
> with user sign-off, per-story fail-to-pass and pass-to-pass cases with
> stable IDs, the deterministic-first grading ladder, cost-tiered runs,
> sha256-receipted evidence cited by gate manifests, and eval failures
> iterating through the factory loop) is authored in the expansion milestone
> and will replace this body. Until then, do not rely on this skill for eval
> setup or story evaluation.

Intended scope, so readers know what is coming: `sf-eval` makes evals a
precondition of work, not an afterthought. No story enters the queue before
its eval suite is signed off by the user, and no story is done until its
eval cases pass or an approved override is on record. The eval policy module
lives with the other principles at
`.software-factory/context/principles/evals.md`.
