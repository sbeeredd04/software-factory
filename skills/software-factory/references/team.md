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
| `sf-design-reviewer` | Applies the four `sf-design` skills as the anti-bloat bar on plans and diffs |
| `sf-engineer` | Standard implementation plus tests; smallest complete change |
| `sf-principal-engineer` | High-risk or complex work: auth, money, state machines, migrations, concurrency |
| `sf-qa-engineer` | Exercises acceptance criteria on the actual HEAD: effects, recovery, regression |
| `sf-code-reviewer` | Reviews the actual diff with cited anchors; never authors the reviewed work |
| `sf-evaluator` | Calibrated qualitative evals; runs known-good/bad canaries first |
| `sf-ai-engineer` | Prompts, context, tools, evals and harness boundaries |
| `sf-release-engineer` | CI/CD, pipelines, gated sequential merges, deploy-SHA proof |
| `sf-security-reviewer` | STRIDE/OWASP review on risky diffs |

The PM, architect and QA roles use BMad skills only when BMad is installed; when
it is absent they do the same job natively with the pack's own templates. A small
change may need none of them. Architecture consultation is for unresolved
contracts, not every function.

## Best-fit routing

Choose by capability, risk, reliability, latency and likely total rework — not by
price or by habit. Record the requested model, the effective model when the host
reports it, and a one-line route rationale. Never infer a model version from an
alias and never invent model IDs. When a capability is unavailable, use a
suitable fallback or report a concrete gap — the answer is not weaker proof.

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
