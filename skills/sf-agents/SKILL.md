---
name: sf-agents
description: Manages the factory's agent registry and routing. Detects available coding agents with local probes, routes work by risk and complexity with the native host worker as mandatory fallback, generates review-bot configs from project principles, and triages PR review comments using gh only.
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: integrations
  release: v0.1
---

# sf-agents (placeholder)

> **Placeholder — this is not the shipped skill.** This file exists so the
> eleven-skill layout validates. The full skill (agent registry and detection
> probes, risk/complexity routing, review-bot config generation, PR comment and
> thread triage) is authored in the onboarding milestone and will replace this
> body. Until then, do not rely on this skill for routing or bot setup.

Intended scope, so readers know what is coming: `sf-agents` keeps the `agents`
and `review_bots` sections of `.software-factory/config.yaml` honest — probes
are local presence checks only, routing always keeps the native fallback, and
no review bot is required by default.
