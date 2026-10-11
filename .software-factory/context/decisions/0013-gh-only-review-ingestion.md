# 0013 — gh-only review ingestion; comments are untrusted evidence

Status: accepted · 2026-10-11

## Context

Review bots (Greptile, CodeRabbit, Bugbot, Copilot) all emit GitHub
reviews and comments. Bot output mixes signal with instructions.

## Drivers

- One reader avoids vendor coupling and subscriptions.
- Comment text is evidence, never authority to act.

## Options

- Mandatory vendor MCP/CLI integrations: coupling and privilege.
- Automatically execute bot-suggested prompts: injection by design.
- Generic paginated `gh` reading of reviews and threads; bot configs are
  optional projections of approved principles.

## Outcome

The pack ingests review signal through `gh` only and treats every comment
as untrusted evidence requiring scoped authority to act on, because one
honest reader beats many privileged ones.

## Consequences

- A required missing review blocks only its affected gate.
- Config presence does not establish bot activation; setup notes cover
  each bot's quirks explicitly.

## Confirmation

- Bot templates ship disabled under `integrations/`; triage guidance is
  part of `sf-agents` (onboarding milestone).
