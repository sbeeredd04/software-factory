# Routing by task and actual scope

Use existing config fields: coding default, optional low/medium/high complexity
override, independent_review and mandatory native fallback. Do not create a
second route DSL. Every registered agent declares allowed risk tiers; the native
fallback supports all four, but that declaration grants no authority.

- Analysis/review: independent_review then native, requiring observed read-only
  restrictions when the assignment requires enforcement.
- Routine coding: complexity override, coding default, native. Deduplicate;
  selecting native directly ends the chain. Require observed workspace-write
  scope and the exact claimed worktree.
- Sensitive mechanics: principal-engineer expertise, current contracts and
  independent review; risk eligibility does not replace these requirements.
- Irreversible work: obtain the applicable owner decision before effects. Native
  fallback is retained but cannot bypass that checkpoint.

Weigh task fit, reliability, likely rework, complexity, risk and permission
scope. No cheapest-first rule, fixed model mapping or mandatory team size.
Record the reason, role/skill, requested model and actually reported effective
model in the existing agent-attempt receipt. Unknown model stays null.
A different reviewer identity must inspect the actual author's diff and HEAD;
a different model alone does not prove independence.

The deterministic helper makes a **proposal**, not a dispatch or authorization:

```sh
python3 -I -B scripts/agents.py --project /project route --request /private/route.json
```

A request contains `risk` (0–3), `complexity` (`low|medium|high`), `operation`
(`observe|write`), `phase` (`coding|review|analysis`), `observations` from discover,
and optional `permissions` (agent ID to observed `read-only|workspace-write`).
Set `denied: true` after an actual permission refusal. The supplied permission
map is a host report, not authenticated enforcement evidence; verify it before
acting. A stale config digest is rejected. Missing permissions produce a gap.

Absent or unsuitable optional backends can degrade to the current native
worker at equivalent allowed scope. A permission failure never selects a
less-restricted backend. Never add `--trust`, `--yolo`, `--approve-mcps`, forced
approval, dangerous sandbox modes or bypassPermissions. Declared recipes do not
create authority; scope and permission changes go through the owner.

A zero-CLI machine can complete local work with observed native scope, native
independent review and ordinary project proof. If enforced independence or
permissions are unavailable, report that particular gap rather than invent it.
The helper neither calls models nor tests a live host. A CLI exit zero would
still require actual diff/effect inspection and the task's tests/eval evidence.

Missing gh affects GitHub publication/triage actions only. With no bots configured,
report `not_applicable`; internal review and CI continue. A required bot's missing
current-head report pauses that gate; optional bots do not block local work.
