---
name: sf-help
description: Sets up the Software Factory in a project. Crawls the codebase (stack, tests, CI, docs, principles, review bots, agents), drafts PRINCIPLES/ARCHITECTURE/CONVENTIONS from templates, asks 20 pre-filled interview questions, then applies the approved setup. Use for first-time setup or re-onboarding.
license: MIT
compatibility: Works with Claude Code, Cursor and Codex. BMad Method v6 is optional and installed separately.
metadata:
  factory-role: onboarding
  release: v0.1
---

# sf-help (placeholder)

> **Placeholder — this is not the shipped skill.** This file exists so the
> eight-skill layout validates. The full onboarding skill (discovery crawl,
> document drafts, the 20-question interview, approved-setup apply, optional
> design audit, first-lap proposal) is authored in the onboarding milestone and
> will replace this body. Until then, do not rely on this skill for real setup.

Intended scope, so readers know what is coming: `sf-help` interviews the
codebase and the human, then writes `.software-factory/config.yaml` (validated
by `scripts/config.py` from the orchestrator skill) plus drafts of the project
principle documents. Nothing is applied before the human approves the drafted
setup.
