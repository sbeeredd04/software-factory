---
name: sf-agents
description: Use to discover agent capabilities, choose risk-aware worker routes, project approved principles into selected review-bot rules, or triage pull-request reviews. Keeps native fallback, preserves user files, and renders commands without executing agents or GitHub writes.
license: MIT
compatibility: Python 3.11+; Claude Code, Cursor and Codex. Full setup supplies helper assets.
metadata:
  factory-role: integrations
  release: v0.1
---

# Agent capabilities and review integrations

Staff the outcome with the available expertise and actual permission scope.
The orchestrator owns staffing, claims, authority and acceptance; this skill
supplies observations, routing rationale and review integration artifacts.

## Principles

Read the repository's own governing principles; they remain authoritative.
Do not create a second format.

Read all four configured modules and the approved config. Missing config routes
to `sf-help`; missing or empty principles block derived rule application. Follow
the entry skill's authority and worker contracts. Eleven shipped roles are a
starting team, not a mandatory fleet or a limit on useful expertise.

## Choose the useful capability

- [Registry](references/agents.md): observe presence without launching binaries.
- [Routing](references/routing.md): fit risk, complexity, permissions and likely
  rework; retain native fallback and record requested/effective models separately.
- [Bot rules](references/bots.md): propose rules derived from approved principles;
  apply only an exact reviewed digest, preserving user configuration bytes.
- [Review triage](references/triage.md): collect every review page through `gh`,
  inspect findings against the current code, and propose authorized responses.

Run helper examples from this skill directory with Python 3.11 or newer:

```sh
python3 -I -B scripts/agents.py --project /project discover
python3 -I -B scripts/render_bots.py --project /project plan --bots copilot \
  --principles-ref 'decision:approved-principles' > /private/bot-proposal.json
python3 -I -B scripts/triage.py recipes --owner example --repo project --number 1
```

Helpers never dispatch agents, query accounts/models, execute bot suggestions,
or call GitHub. The host interprets observations, verifies actual permissions and
handles authorized effects. A displayed recipe or successful process is not
verified work. Use the existing agent-attempt receipt for attribution and route
rationale; use independent review and current proof for acceptance.

## Degradation and return

A missing optional agent routes to the native worker within equivalent allowed
scope. A denied permission stops that action; changing backend never grants it.
A missing `gh` blocks external GitHub work only. With no configured bots, report
`not_applicable` and continue local work, internal independent review and CI.
A missing required bot report blocks only its affected gate.

Return observations and their sources, selected route and rationale, exact
proposal/diff and source hashes, proof on the current HEAD, and gaps with one
next action. Auth, model access, vendor activation and effective settings remain
unknown unless actually observed. Never claim live host compatibility from
static projections or fixtures.
