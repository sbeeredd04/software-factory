# Twenty setup decisions

Crawl first, interview second. These are twenty answer slots, not a bulk form.
Prefill from discovery and prior answers. Ask one unresolved material question at a
time. Accept-all-defaults is one action; “you decide” takes a safe default. Confirm
already answered keys in one line each, never re-ask them. Unknown authority stays
unknown. Greenfield skips repo inference questions and marks structural answers
set-when-the-repo-exists. Escalate conflicting conventions with a recommendation.

Keys below are canonical config paths; named maps are represented by their parent
key. Qualitative policy lives in referenced documents, not duplicate config fields.

## Group A — Autonomy, authority and risk

### Q01 — How should the factory carry approved work forward?
Why: The continuing loop needs clear scope and material decision boundaries.
Default: Risk-adaptive continuous delivery; local edits and commits within approved intent, with source-linked scoped acceptance authority.
Keys: autonomy.mode, autonomy.local_edits, autonomy.commits, autonomy.standing_delegations

### Q02 — Where may proven changes integrate?
Why: Branch selection is an authority boundary.
Default: Propose dev and protect main; actual remote protection remains unknown until observed.
Keys: branches.integration, branches.protected, branches.story_prefix

### Q03 — Which actions have standing authority?
Why: Availability does not grant permission to push, publish, deploy or repair production.
Default: External writes remain disabled unless an applicable source-linked owner decision covers them.
Keys: autonomy.push, autonomy.open_pr, autonomy.merge_integration, autonomy.deploy, autonomy.standing_delegations

### Q04 — What continues when a decision is blocked?
Why: One dependency should not idle unrelated approved work.
Default: Continue demonstrably independent approved work; pause only dependent work.
Keys: autonomy.blocked_behavior

### Q05 — What worker capacity and owner ceiling apply?
Why: Concurrent work must fit observed host resources.
Default: No owner ceiling; actual host capacity still bounds dispatch, unknown capacity means conservative dispatch.
Keys: budgets.max_parallel_workers

## Group B — Proof, environments and CI

### Q06 — Which environments and signals may we access?
Why: Delivery and observation each need scoped access and real capability.
Default: Preserve known targets; monitoring disabled until source access, data policy and window are approved.
Keys: environments, operations.enabled, operations.sources, operations.authority_ref, operations.until, operations.schedule_request

### Q07 — What proves delivery and triggers follow-up?
Why: Completion and later regression need observable conditions.
Default: Actual artifact identity and affected behavior; no invented operational thresholds or permanent monitoring.
Keys: verification.deploy_environment, verification.required_checks, verification.risk_requirements, eval, operations.sources, operations.followup

### Q08 — What tests, build and style checks must hold?
Why: Workers and reviewers need a reproducible proof floor.
Default: Discovered commands remain unexecuted declarations until verified; coverage policy comes from conventions.
Keys: environments, verification.required_checks, eval, documents.conventions

### Q09 — Which CI checks are required?
Why: Workflow files do not establish remote branch requirements or successful runs.
Default: Required remote checks unknown until observed; missing CI needs explicit applicability decisions.
Keys: verification.required_checks, verification.risk_requirements, project.repositories

## Group C — Agents, routing and review bots

### Q10 — Which expertise and models fit each risk tier?
Why: Risk and reviewer independence matter beyond binary presence.
Default: Native fallback with conservative observed capacity; external auth and effective model identity remain unknown.
Keys: agents, routing.coding, routing.complexity, routing.independent_review, routing.fallback

### Q11 — Which bots and reports should participate?
Why: Configuration presence does not prove bot access or current-subject review.
Default: Preserve existing bot files; no required bot until confirmed; zero bots is valid.
Keys: review_bots

### Q12 — How should approved changes be integrated?
Why: A single integration owner must follow the repository's review surface.
Default: Merge into the proposed integration branch through review; no direct protected-branch push.
Keys: branches.merge_method, branches.direct_push, autonomy.push, autonomy.open_pr, autonomy.merge_integration

### Q13 — Which spend and stall alarms apply?
Why: Detect repetition and cost without silently abandoning the task.
Default: Alarm-only, three stall repetitions; unobservable spend is unknown.
Keys: budgets.mode, budgets.warn_usd_per_run, budgets.stall_repetitions

## Group D — Principles, style and design

### Q14 — Approve or adjust the grounded document drafts?
Why: Later decisions need durable product, architecture and convention authority.
Default: Preserve existing documents; draft only missing content with source anchors and explicit unknowns.
Keys: documents.principles, documents.architecture, documents.conventions, documents.extra_context

### Q15 — What design and bloat standards should guide work?
Why: Shared quality expectations prevent unnecessary systems and inconsistent reviews.
Default: Reuse current contracts, smallest complete change, meaningful proof; optional design audit off.
Keys: documents.principles, documents.conventions

### Q16 — Which commit and PR conventions apply?
Why: Authored changes should match the repository's contribution practice.
Default: Existing contribution rules and PR template; conflicting answers need an explicit decision.
Keys: documents.conventions, documents.extra_context

### Q17 — How should progress and monitoring changes be reported?
Why: Evidence should be visible without repetitive notification noise.
Default: Concise milestone and blocker updates; meaningful operational changes only, destination explicitly approved.
Keys: reporting.style, checkpoints.transitions, operations.notifications, operations.authority_ref

## Group E — Planning, BMad and durable context

### Q18 — How much planning does this outcome need?
Why: Small work can stay small while preserving risk and proof floors.
Default: BMad planning with structured epics/stories and adaptive depth; native requires an explicit choice or preserved approved legacy route.
Keys: planning.method, planning.depth, tracker.adapter, tracker.path

### Q19 — Reuse BMad or request the pinned optional provisioning?
Why: Existing planning must survive setup and network installers need separate consent.
Default: Preserve detected artifacts; report missing BMad and offer separately authorized pinned provisioning. No silent native fallback.
Keys: bmad.install_version, bmad.modules, bmad.custom_root, bmad.automatic_updates, tracker.adapter, tracker.path

### Q20 — Where should context, retros and redaction policy live?
Why: Recovery needs durable facts without retaining credentials or raw source payloads.
Default: Durable transition checkpoints with manual false; honor explicit human reservations and consequence-driven escalation. Bounded evidence, epic retros and source-linked retention.
Keys: checkpoints.transitions, checkpoints.manual, checkpoints.before_reset, checkpoints.before_external_write, checkpoints.retro_cadence, context.retention, context.redaction, extensions, operations.sources
