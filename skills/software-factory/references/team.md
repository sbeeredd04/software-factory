# Team and staffing

Phase: staffing — choosing who does the work, at every point in the loop.

The orchestrator owns the team, not just the dispatch: choose the expertise,
compose bounded assignments, supply fresh context, inspect results, adjust
staffing and resolve technical direction. Agent-first means judgment enabled by
grounding and proof, not a fixed roster with per-role scripts.

## The shipped starting team

Eleven role prompts ship in the pack (`agents/sf-*.md`). They are a starting
team you staff from as needed — not a mandatory fleet, and not a per-story
checklist. You may employ any agent, role or skill the job needs, including
ones not shipped here.

| Role | Focus |
| --- | --- |
| `sf-product-manager` | Outcomes and acceptance criteria; uses BMad PM/PRD skills when installed |
| `sf-architect` | Cross-module contracts and boundaries; uses BMad architecture skills when installed |
| `sf-design-reviewer` | Applies the four `sf-` design skills as the anti-bloat bar on plans and diffs |
| `sf-engineer` | Standard implementation plus tests; smallest complete change including error/recovery and obsolete paths |
| `sf-principal-engineer` | High-risk or complex work: auth, money, state machines, migrations, concurrency |
| `sf-qa-engineer` | Exercises acceptance criteria on the actual HEAD: effects, recovery, regression, compatibility; uses BMad TEA when installed |
| `sf-code-reviewer` | Reviews the actual diff with cited anchors; never authors the reviewed work |
| `sf-evaluator` | Grades calibrated qualitative rubrics after deterministic effect checks; runs known-good/bad canaries first |
| `sf-ai-engineer` | Prompts, context, tools, evals and harness boundaries, without duplicating lifecycle or status machinery |
| `sf-release-engineer` | CI/CD, pipelines, gated sequential merges, deploy-SHA proof |
| `sf-security-reviewer` | STRIDE/OWASP review on risky diffs |

The PM, architect and QA roles use BMad skills only when BMad is installed; when
it is absent they do the same job natively with the pack's own templates. A small
change may need none of them. Architecture consultation is for unresolved
contracts, not every function.

## The skill palette

The eleven skills are stated once, as the capability map in the
[entry](../SKILL.md); this file deliberately does not re-enumerate them. Like
the roles, they are a starting palette — you may use any skill the job needs,
shipped or not.

## Workstreams

Work is organized into parallel workstreams, all visible on one board; the
frontier rule (every unblocked, unclaimed candidate is offered) is owned by
[planning](planning.md). Staff each stream independently by its risk profile —
a stream is a staffing unit, not a reason to serialize — and let claims keep
paths exclusive across streams. R&D is first-class: when a task needs a spike
or technology research, it gets its own story (type `spike`) with the same
claim, receipt and review discipline, and its findings land as decision
records in `context/decisions/` so the next story starts from them.

## Best-fit routing

Choose by capability, risk and likely total rework — not by price or habit.
Record agent, role, skill, requested model, observed effective model and a
one-line route rationale in the optional [agent-attempt receipt](handoff.md#agent-attempt-receipts).
Never invent model IDs. Risk tiers and the native fallback are owned by `sf-agents`;
an unavailable capability degrades to the fallback or a concrete gap report,
never to weaker proof.

Keep authorized streams moving: wait on actual worker handles, inspect their
returns, arrange independent verification, recover failed attempts and refill
freed capacity from the ready frontier. A report of completion is a handoff to
verify, not acceptance; attribution and progress remain visible on the board.

## Independence

Authors self-test and inspect their own diffs; an independent reviewer or QA
accepts the work. Give the reviewer the real plan, diff, HEAD and evidence, not
the author's summary. A different model family for the reviewer is useful when
available, but model diversity never replaces an independent role inspecting the
actual artifacts.

## Worker contract

Every worker, whatever its role, gets a brief and returns evidence in the shape
described in [handoff](handoff.md). Workers may use further expertise within
their scope rather than following rigid step scripts. Acceptance, publishing,
deployment and human communication stay with the orchestrator.
