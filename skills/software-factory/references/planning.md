# Planning and readiness

Phase: planning — from grounded intent to an approved, story-sliced plan, and
the ready-frontier decision that follows it.

## Grounding

Read the project's configured principles and architecture documents, the
per-story board records and the tracker that feeds them, and the current code
before planning. Planners and workers alike start from the project-context
home: the configured principles together with
`.software-factory/context/CODEBASE.md`, the generated codebase map owned by
[sf-crawl](../../sf-crawl/SKILL.md) — refresh it with `sf-crawl` when it is
missing or stale. Reuse existing approved plans and GO decisions; fill only the
actual gaps. Missing product outcomes or acceptance criteria benefit from the
product manager; changed cross-module contracts from the architect; these are
examples, not compulsory staffing.

When BMad is installed, its planning skills do the heavy lifting: PRD or spec
work for genuinely missing planning, architecture skills for contract changes,
and the ticket/sprint artifacts to slice an initiative into epics and stories.
When BMad is absent, plan natively with the same discipline: outcome, acceptance
criteria, stories, proof per story. The orchestrator keeps ownership of design
and acceptance either way. Installation, provenance and partial-effect recovery
are described in [BMad provisioning](bmad-provisioning.md).

## What a plan names

Map the request to acceptance criteria and current modules: responsibility
owners, boundaries, data flow, contracts, obsolete paths to delete,
compatibility and non-goals. Use `sf-design` and its focused skills
(`sf-smell-audit`, `sf-refactor`, `sf-patterns`) during planning to reach the
simplest complete design, and hold the anti-bloat bar: reuse first, the smallest
complete diff, no unrequested abstraction, obsolete-path deletion as part of
done, and one runnable check per story.

Risk includes auth, money, privacy, state and concurrency, migrations,
deployment and user-visible behavior. Each story names its failure, unknown and
recovery cases; its deterministic tests; its actual-effect assertions; any
qualitative eval slice; its staging or deploy flow; and its rollback. Doc-only
or non-deployable work carries an explicitly approved narrower proof, not a
silent exemption.

A story enters the queue eval-ready: it carries `fail_to_pass` and
`pass_to_pass` cases with stable, story-linked IDs drawn from the per-surface
suites the user has signed off. `sf-eval` owns the suite setup, the case shape
and the grading ladder; planning's job is to keep unevaluated scope out of the
queue.

Ceremony scales with risk: a small low-risk change gets a small spec and the
relevant proof, not the full apparatus.

## Independent plan review

A non-author reviewer receives the actual sources, code anchors, acceptance
criteria and risks — not the planner's summary. Material acceptance or risk
findings force revision; re-review the affected portions until the gaps resolve
or the human owner decides. Iterations are bounded; do not optimize for cosmetic
perfection.

Reuse a scoped GO when it covers the request; new scope or authority escalates
per [authority](authority.md).

## Ready frontier

Readiness is defined by dependency-unlock evidence — each prerequisite's unlock
condition demonstrably holds — never by story title, list order or position in a
tracking table. Ready work across eligible epics may overlap within the approved
scope and the human checkpoint gates. Brief each dispatch with actual file
scope, dependency evidence, acceptance criteria, proof expectations and any
phase-scoped resources. Schedule by coupling, current capacity and observed
rework, not by a global order.

The board makes this mechanical: `roadmap.json`'s frontier is computed from the
`after` graph (review counts as met for starting, epic gates wait for human
acceptance), spans every stream at once, and carries the cross-stream
diagnostics. Workstreams run in parallel; the frontier offers all unblocked,
unclaimed candidates rather than one global next story. The readiness rule, the
transition table and the regeneration command live in
[recovery](recovery.md) — stated there once, never restated here.
