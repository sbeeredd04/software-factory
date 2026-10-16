# Software Factory architecture

Proposed setup document grounded in the canonical source and accepted decisions.
It describes the existing portable product; it does not accept an epic or claim
that an unobserved host, remote integration or deployment has succeeded.

## System and boundaries

The active coding host owns judgment, model selection, native workers, tool
permissions and continuous execution within approved scope. Canonical Markdown
skills and role prompts supply the method. Standard-library Python preserves
bounded facts and checks evidence. There is no separate model client, scheduler,
daemon, telemetry collector or workflow service (ADRs 0001 and 0021).

`skills/` and `agents/` own portable instructions; `hosts/` owns host policies.
`install.py` generates consumer projections, runtime helpers and ownership data.
`schemas/` owns strict data contracts. Tracker adapters read planning inputs and
propose exact patches; the board remains the single story-status authority.

## Data ownership and lifecycle

- Config: `.software-factory/config.yaml`; setup evidence is separate from status.
- Governing principles: the four existing configured modules in `principles/`.
- Board: committed per-story/epic records in `.software-factory/context/board/`.
- Claims: ignored active run state, exclusive paths and explicit owner release.
- Evidence: ignored subject-bound receipts, actual check outputs and decisions.
- Dashboard and lifecycle graph: regenerable views of authoritative records;
  declarations and provenance do not authenticate users or prove external effects.
- Decisions: canonical accepted ADRs under `decisions/`; real source authority
  is reconciled by the orchestrator, never inferred from an actor label.

The host grounds intent, prioritizes, uses BMad epics/stories, claims eligible work,
staffs workers and independent reviewers, tests and repairs, integrates and proves
effects, then feeds authorized observations into the next cycle. Assess risk,
affected assets, reversibility and requested autonomy at any phase (ADR 0027).
Human escalation is conditional; current finite delegation and independent
consequence review permit protected orchestrator epic acceptance. Required proof
and explicit reservations remain binding (ADR 0023). Historical records stay
historical; in-review is neither built nor merged. A decision blocks its dependents.

## Installation and optional capabilities

Full project setup projects skills, role prompts, policies and recovery hooks.
Raw portable discovery is skills-only. Native marketplace bundles are generated
self-contained release artifacts, never hand-edited or committed (ADR 0024).
Host invocation/trust/permission limits are explicit (ADR 0022); local fixtures
and format checks do not establish live cross-host loading.

BMad is the selected planning method, installed separately via its official route.
Installation and actual planning execution are separate observations. Preserve
existing/partial installations. The approved fresh route pins core/BMM 6.12.0,
TEA v1.27.2, BMB v2.2.2 and CIS v0.3.2 (ADR 0025). Explicit native selection or
scoped fallback requires equivalent planning, acceptance and proof; missing BMad
never silently selects it. Existing approved planning artifacts remain reusable.
No automatic updates.

Bots, external agent recipes, extensions and monitoring are optional declarations.
The host confirms actual capability, permissions and requested/effective models.
Monitoring stays disabled pending source, scope, window, trigger, data policy,
destination and follow-up authority. Registration does not grant access.

## Evidence, delivery and recovery

Use Python >=3.11 and the contribution guide's actual full static gate,
`bash scripts/check_all.sh`, plus affected behavior/regression proof. The pack's
single eval owner is `evals/eval.config.json`; configuration links it as context
instead of duplicating its cases or approval record.

Work occurs on `codex/*` feature branches; pull requests target `dev`; a maintainer
integrates. No configured remote, remote CI, merge, publication or production
result is established by this setup. The non-deployable pack's completion-phase
local staging equivalent and any reserved checkpoints still need scoped decisions.
Candidate disposable-consumer proofs remain candidate proofs until then.

Resume reconciles claims, dirty work, subjects and uncertain external effects.
Preserve user edits, failed evidence and partial setup; do not retry uncertain
external outcomes blindly. Retros propose bounded improvements for independent
review and tested application through the owning transaction.
