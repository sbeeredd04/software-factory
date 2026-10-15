# Software Factory v0.1 delivery proposal

> Historical planning record. Its proposed and pending language below describes the state when drafted. [ADR 0023](../../.software-factory/context/decisions/0023-evidence-bound-transitions.md) has since authorized protected built/done and source-linked checkpoint checks, implemented in `roadmap.py` and `gate.py`; the [verification guide](../verification.md) states their present limits. The three administration skills and derived `trace.py` graph are implemented, and setup reuses confirmed facts across twenty catalog slots without twenty fresh questions. The [dogfood account](../DOGFOOD.md) records later real work. Exact staging applicability, human acceptance and publication remain separate decisions. Do not use this historical plan as the live board.


Delivery plan, updated after the owner's clarification. [ADR 0021](../../.software-factory/context/decisions/0021-continuous-host-orchestration.md) records the portable, continuous host-owned loop with visible progress; the owner also explicitly requested the derived SDLC graph. The plan preserves the full remaining v0.1 outcome: an installable, documented eleven-skill and eleven-role pack that takes a grounded request through implementation, independent proof, integration, release evidence and a human checkpoint. The implementation remains Markdown and standard-library Python. Protected state-transition enforcement and final release authority retain their separate decisions below.

## Approval and evidence baseline

**Existing scope:** stories 20–24 complete installer/host support; 25–28 complete configuration and administration; 29–33 complete the showcase, assets, documentation, README and publication. Earlier work remains part of the release and must retain its evidence. Current work on host ownership bookkeeping, lint and freshness is a bounded repair within the existing installer effort.

**Existing dependency order:** 19 → 20 → 21 → 22 → 23 → 24 → 25 → 26 → 27 → 28 → 29 → 30 → 31 → 32 → 33, plus the existing epic prerequisites and acceptance rules. This proposal does not replace those edges. Native specialists can investigate independent questions within the current story now; fresh specialists can review its actual plan, diff and proof at the appropriate gates. That is not concurrent dispatch of the later stories. Research, source inspection and draft acceptance design may proceed independently; implementation dispatch must honor the recorded dependencies and claims. Concurrent chain work requires an owner-approved dependency-contract rebaseline, not just unused agent capacity.

**Proposed additions:** enforce evidence and ownership invariants, expose a derived lifecycle graph, and make operational failure/recovery a demonstrated part of the dogfood story. These fit existing skills; they do not add a twelfth skill or a hosted runtime.

**Remaining owner decisions:** mechanically enforcing the proposed protected acceptance transitions and source-linked required checkpoints; the pack's exact completion-phase local staging equivalent; any changed original story dependencies or acceptance cadence. The portable product direction is resolved. Earlier validators' success is not human acceptance. Foundation and Expansion acceptance must be reconciled against actual owner decisions before being treated as complete.

**Implementation progress:** the claim handoff wording now retains ownership until review submission; story updates are serialized and corrupt ownership suppresses readiness (story 42); audit recognizes historical evaluation IDs and accounts for invalid entries (story 41). Those repairs have independent source review and targeted proof. Protected board transitions still do not invoke the evidence gate, and checkpoint flags remain advisory. The proposed matrix below addresses those remaining limits; ordinary local green checks do not establish them.

## Workstream 1 — trustworthy progress and evidence

**Outcome:** the owner can trust a ready candidate, transition and completion claim, including after interruption or concurrent updates. Existing ownership and audit defects are being repaired within their documented contracts. The protected acceptance-transition changes remain a separate sensitive-mechanics decision.

**Scope:** extend existing board/state/gate contracts under `software-factory` and receipt handling under `sf-eval`. Use draft proposal labels P-GATE, P-CLAIMS and P-CHECKPOINT until the owner approves board entries. Preserve stable IDs, frozen terminal history and the single story-status authority.

**Acceptance and proof:**

- A protected acceptance transition evaluates the required gate against the actual subject and receipt digests. Missing, stale, failed, unknown, tampered or infrastructure-error evidence cannot produce an ordinary successful transition. The exact transitions, applicability and override treatment need owner approval.
- Two writers updating one story cannot silently lose a receipt or status update: a serialized transaction or explicit revision conflict preserves both the authoritative record and an actionable retry path. Test the contested update with separate processes, not only sequential calls.
- Missing, unreadable or invalid claim authority yields unknown/blocked dispatch eligibility; it does not imply unclaimed work. The last good projection remains readable but is explicitly stale.
- Demonstrate an approved claim lifecycle through implementation, evidence submission, review and release. Recommend retaining the claim until the worker reaches in-review, then releasing after handoff reconciliation; any alternate post-release transition needs an explicit owner/token contract.
- Required checkpoints cite durable, source-linked owner decisions and are structurally checked at approved boundaries. A local `--actor human` value is caller-supplied metadata, not authentication; file/schema validation cannot prove who supplied a decision or stop an authorized local process from changing it. The orchestrator must reconcile the decision with the trusted user conversation or approval surface. Host controls, repository protection and real permissions provide authority boundaries. Reusing an existing valid scoped decision must work without repeated prompts.
- A changed base or subject invalidates only the affected evidence; unrelated valid receipts remain usable. Unknown merge/deployment outcomes require provider reconciliation before retry.
- Run audit recognizes existing historical eval run IDs, including uppercase `T`/`Z`, under a distinct run-entry contract while leaving program-ID rules unchanged. Every safely inspectable real entry contributes to byte accounting even when its name is invalid; invalid entries also receive diagnostics. Keep existing evidence in place: no rename migration or deletion. Fixtures prove valid historical IDs, invalidly named real entries, correct totals and safe treatment of symlinks/unreadable entries without following paths outside the audited root or claiming a complete count when inspection is incomplete.

**Approved transition matrix (ADR 0023):** the rows below describe structural preconditions, not an authenticated authorization service. They retain the current status vocabulary. Each decision reference must identify its trusted source, scope, subject or approved scope digest, decision, and time; a missing, contradictory or out-of-scope decision is unresolved.

1. **`backlog → ready-for-dev` — orchestrator:** a current plan with story acceptance/eval cases exists; a source-linked scoped GO covers the work; prerequisite unlock evidence satisfies the existing `after` rule, including review-counts-as-met and applicable epic gates; claim authority is readable/valid; and any `plan_checkpoint` has its scoped decision reference. Readiness does not acquire a claim. Unknown claim authority cannot produce dispatch eligibility.
2. **`ready-for-dev → in-progress` — assigned worker:** readiness is rechecked against current source state and the worker holds the valid exclusive claim for this story and its exact scope. Record baseline/subject identity before edits. Conflicting or unknown ownership blocks the transition.
3. **`in-progress → in-review` — owning worker:** the worker still owns the valid claim and submits receipts bound to the actual review subject. Record the review handoff before release. Release follows reconciled handoff; it cannot erase receipts or serve as review approval. Independent reviewers inspect that subject and its actual evidence. A released claim does not authorize later author writes; revision work must regain valid ownership.
4. **`in-review → built` — orchestrator:** every story prerequisite must be done and every applicable epic gate accepted, preserving the current integration-order rule; then verify the applicable premerge gate manifest, cited receipt integrity and verdicts, independent review and required checks against the recorded full candidate SHA. Record the manifest identity/digest and subject. A changed subject requires the affected proof to be refreshed. `built` records successful premerge acceptance, not a completed merge or deployment.
5. **`built → done` — orchestrator:** reconcile actual integration, verify the applicable integration and complete-phase manifest requirements, and bind receipts to the full merge SHA and the resulting artifact/environment identity. Required effect proof uses the approved deployment or exact-revision local staging equivalent. Any story `hitl` or `done_checkpoint` requires a scoped, source-linked owner decision before completion. An open PR, pending merge, failed effect check or unobserved external outcome cannot become done.
6. **Epic acceptance — owner decision recorded by the orchestrator:** all required descendant evidence and epic applicability requirements are satisfied, and a durable acceptance record links to the owner's trusted source and exact reviewed scope. Check the record structurally and reconcile its source before updating the epic. Do not claim the local actor field authenticates the owner. Preserve accepted decisions and supersession history rather than silently rewriting them.

**Review and proof failures:** retain the rejection and review history; return confirmed findings to the owning worker. Revision work reacquires or retains valid ownership before edits, moves back to an approved in-progress attempt, and refreshes the affected subject-bound proof before another review. A failed gate leaves progress unchanged; it never silently advances the record.

**Override applicability:** all rows consume the same approved gate rules for exclusions, narrower applicability and overrides. A record cannot turn failed/unknown evidence into ordinary passing evidence. Any allowed override retains its original verdict, reason, scope, decision source and artifact binding, and produces the gate's explicit approved disposition. Missing or invalid authority, out-of-scope overrides and forbidden exceptions block the transition. The exact supported gate dispositions and treatment of existing records must be reviewed before implementation; a new convenience path may not bypass the gate.

**Failure/recovery:** malformed records, crashed writer, interrupted checkpoint, missing receipt, stale base, revoked authority and unknown external effect each have a deterministic scenario and expected safe next step. Preserve prior records on failed writes. Report the difference between structural receipt integrity and the truth of an observed effect.

**Checkpoint:** the owner approved the policy/transition proposal in ADR 0023; a principal engineer implements and an independent reviewer verifies it. The owner accepts the demonstrated boundary cases before the product claims the kernel checks them. Claims distinguish structurally checked provenance from authenticated authority and real effect truth. Existing review-counts-as-met dependency semantics stay intact unless separately amended.

## Workstream 2 — finish installer and host lifecycle, stories 20–24

**Outcome:** a consumer installs the same canonical pack for the chosen host, understands limitations, and can update or remove owned projections safely.

**Preserved stories and acceptance:**

- **20, Cursor and Codex projections:** host-only outputs contain no foreign-host files; combined and sequential installs converge in both file content and ownership metadata; shared skill payloads are owned consistently. Six entry/admin skills remain explicit-only, while the five working skills retain their approved classification. Codex agent projections omit fixed models. Golden files and PATH guard stubs prove the expected formats and that no host CLI was executed.
- **21, session-start/pre-compact hooks:** run the exact installed hook command strings against fixture inputs. No active pointer means inert behavior; active recovery yields a short host-correct pointer without granting authority; corrupt state is sanitized; duplicate adapters do not double-inject recovery; pre-compact failures do not block. Test stdout envelopes and diagnostic transport separately.
- **22, uninstall and doctor:** a dry-run enumerates owned changes; apply removes only unchanged owned files and restores eligible backups. User changes, context, principles, configuration, overlays, runs and BMad survive. Doctor reports pass/warning/blocked/unverified with repair guidance and observes drift, audit findings and missing/stale projections without silently repairing them. Trust is never invented.
- **23, pinned BMad provisioning:** retain the approved 6.12.0 pin and official installer boundary. Prerequisite absence or versions below the floor produce an honest degraded profile; existing installations are detected and reused; skip works; resolved module versions are recorded. Mocked argv tests and a separately labeled, network-marked official-installer run prove different things. A skipped network test stays unverified.
- **24, distribution:** portable source discovery is skills-only and native marketplace manifests resolve to real paths inside self-contained generated release artifacts (ADR 0024); output is reproducible; bootstrap verifies archive integrity before execution and rejects a tampered archive without running its contents. Local argument forwarding works. Canonical discovery finds eleven skills. Generated `dist/` remains untracked, as required by current repository policy.

**Failure/recovery:** interrupted writes, moved checkouts, edited owned files, stale manifests, missing prerequisites, network failure, existing BMad and digest mismatch preserve user content and return actionable results. Review snapshots or manifests before retrying an uncertain install.

**Checkpoint:** retain the Installer and Hosts epic acceptance after story 24. Story-level proof can be reviewed earlier without declaring the whole epic accepted. No tests launch `claude`, `cursor-agent` or `codex`, even for version detection.

## Workstream 3 — usable onboarding and administration, stories 25–28

**Outcome:** a new or existing project can configure the pack, establish concrete acceptance suites, route available expertise and retain approved customizations across reinstall.

**Preserved stories and acceptance:**

- **25, configuration and adapters:** strict versioned schemas and semantic validation agree with every labeled valid/invalid fixture. Paths resolve independently of working directory; secrets, bypass settings, absent native fallback and integration/protected-branch conflicts are rejected. Explain the distinction between harness `file_state` and grading `state`. BMad v6 and Markdown are planning inputs; board records retain status authority. The v7 adapter remains an honest read-only stub.
- **26, sf-help:** replace the placeholder; reuse the existing crawl artifact instead of making a second crawler. Python, TypeScript and greenfield discovery fixtures expose known facts and unknowns. Preserve the approved twenty grouped questions, rationale/default/config mapping, one-at-a-time interaction and accept-defaults path. Setup is previewable, approval-scoped, valid by construction and idempotent. A shorter adaptive interview is an optional future amendment, not assumed scope.
- **27, sf-agents:** replace the placeholder with capability inventory, risk/complexity routing, requested/effective route records, native fallback and honest unavailable states. No actual host CLI probe runs in repository tests. Deterministic bot rendering preserves user sections and records provenance; zero configured bots is supported. Triage reads complete findings, distinguishes actionable issues and records dispositions. External resolution or posting follows explicit authority.
- **28, sf-evolve:** replace the placeholder with credential-free skill/MCP registration and root-contained overlays. Matching base hashes reapply; changed bases are reported stale without overwriting. BMad customization uses its supported override path with recursion protection. A retro produces a proposed patch, independent review and tested application; governing policy changes require a named owner decision.

**Failure/recovery:** absent optional tools, unsupported tracker versions, conflicting setup, invalid configuration, changed overlay base and unavailable models fail or degrade explicitly. None weakens proof or silently increases permissions. Consumer modifications remain recoverable.

**Checkpoint:** retain Onboarding and Integrations epic acceptance after story 28. Approve project principles and per-surface evaluation suites before dispatching that project's first story; a reused scoped approval should not trigger a new interview.

## Workstream 4 — derived full-SDLC graph

**Outcome:** the user can answer what is ready, why work is blocked, which requirement lacks proof, which evidence a change invalidated, what shipped and what still needs human judgment.

**Proposed scope:** add a versioned derived projection using existing code-map and lifecycle artifacts. Candidate nodes are requirement/assertion, decision, epic/story, code surface, claim, receipt, finding, commit/PR, deployment/effect and checkpoint. Candidate edges are depends-on, covers, implements, verifies, reviews, supersedes and deployed-as. Keep model selection in the host and graph computation in bounded deterministic helpers.

**Acceptance and proof:** every edge has a source anchor and explicit provenance; unknown relationships stay unknown. Board records own status, claims own write exclusivity, receipts own observed checks, and decision records preserve approval provenance for reconciliation against the trusted source. Rebuilding from identical inputs yields identical graph content. Deleting the projection loses no source facts. A changed subject exposes stale evidence rather than changing source records. Missing sources and dangling references produce actionable diagnostics. Reject cycles only where the relevant contract requires acyclicity: task prerequisites and decision/evidence supersession chains. Preserve genuine call/import cycles as factual code relationships and optionally highlight them for design review; they do not invalidate the overall graph. Bounded fixture graphs demonstrate all seven user questions, a rejected prerequisite cycle and a retained factual import cycle; code-language coverage remains explicit. Existing workflow Mermaid and dashboard views link to the same facts.

**Failure/recovery:** interrupted regeneration leaves the last valid projection; invalid inputs cannot produce an apparently current graph. The projection is rebuilt after source repair. No graph database, daemon, semantic embedding service or second mutable status store is introduced.

**Dependencies/checkpoint:** story 43 implements the explicitly requested graph as a derived reader of the existing version-1 board and optional existing crawl JSON, after story 42's consistency repair. It changes neither configuration nor gate policy, so that bounded producer can proceed while installer work continues. Later onboarding integration consumes Workstream 3's completed config contract. An independent reviewer checks derivation/provenance before a manual graph walkthrough. The original 20–33 dependency chain remains intact.

**Current parallel work and future dependency changes:** stories 41 and 42 repair existing audit and ownership contracts; story 43 consumes those fixed version-1 records in a disjoint derived graph helper. Their claimed scopes and actual prerequisite evidence allow overlap with installer work. Preserve the original 20–33 chain. Any future removal or rebaseline of those original edges still requires the dependency-contract decision: explicit input versions, disjoint writes or a serialized shared phase, acceptance cases and actual upstream dependencies. Research drafts cannot declare downstream implementation complete or change host/config contracts.

## Workstream 5 — native dogfood, operations and recovery

**Outcome:** the pack demonstrates its own method on a real change and preserves the chain from a user-visible failure through a verified correction, release proof and follow-up learning.

**Smallest immediate lap:** use the current host-ownership bookkeeping repair within story 20. The concrete behavior is that sequential host installations retain correct ownership and converge to the combined installation. This is an existing user-impacting contract, so no synthetic new feature is needed.

1. Record the request, current scope decision, affected assertions and exact worktree/subject. Independently review a short regression plan before expanding changes.
2. A native worker in the active agent environment performs the bounded fix using ordinary file and Python tools. Run an actual disposable-consumer installation sequence and compare both projected files and manifest ownership. Preserve command output, exit codes and subject-bound receipts.
3. A fresh native reviewer inspects the real diff and another installer sequence; the author cannot approve their own work. An independent failure case must show that user-modified content is preserved or correctly reported.
4. Execute the full repository static gate and affected evaluation cases. Stage only intended paths, prepare the feature-branch PR against `dev`, and follow maintainer integration policy. Record actual merge state; an opened PR is not a merge.
5. With owner-approved local staging equivalence, install the artifact built from the exact integrated revision into a new disposable consumer and re-exercise the affected behavior. Record source/artifact identity, environment and effect evidence. Before a maintainer merge, this proof is candidate-revision proof only.
6. Checkpoint receipts and remaining work. Owner review may accept this story's demonstration; the Installer epic remains pending until its full scope and story 24 checkpoint pass. The next frontier is still computed from existing dependencies.

**What this proves:** actual agent work through native tools, real Python/helper/installer effects and independent review on this host. It does not prove that any projected skill automatically triggers inside another host, or that those hosts execute the projected hooks. Those are statically verified formats and fixture command behavior unless separately observed. Do not launch prohibited host CLIs to fill that gap.

**First complete new-consumer journey:** after stories 24–28 and their required acceptance, demonstrate install → onboarding/default review → signed-off eval cases → one bounded native-agent feature or bug lap → checkpoint → next ready work. Reuse the actual repository journey in story 31; clearly label synthetic examples separately from observed receipts.

**Operational scenarios:** a failing local effect check opens a bug/follow-up record linked to the affected artifact; capture primary evidence, reproduce, correct and revalidate. Demonstrate an approved disposable-environment rollback to a known prior artifact and verify restored behavior. Preserve the failed release evidence. Route findings and a bounded retro into `sf-evolve` or a new board story. No production rollback, recurring monitor or alert-service integration is implicitly authorized.

**Checkpoint:** owner approves the non-deployable pack's local staging equivalent. Any new operational policy or rollback authority is approved before use; each epic still receives its existing human acceptance. Never backfill a missing decision as if it had already occurred.

## Workstream 6 — complete the public experience, stories 29–32

**Outcome:** a visitor understands the method and a new user can follow accurate instructions from installation through their first proven change.

**Preserved acceptance:** story 29 delivers the complete showcase in a coherent design system, local OFL fonts with licenses, all approved capability/loop sections, responsive behavior at 360/768/1440, accessibility and reduced motion, zero console errors and zero external runtime requests. Story 30 produces the declared images from reusable HTML templates with a single regeneration command and verified dimensions, including the 1280×640 social image. Story 31 supplies substantive documentation, four example families, sanitized dogfood evidence, nine diagram sources and an offline link check. Story 32 integrates the pitch, images, host-correct instructions, quickstart, nine diagrams, comparison, limitations and a single shared copy-prompt source.

**Proof:** browser evidence at the three widths, keyboard/accessibility checks, local network request inspection, asset dimension checks, link/diagram validation and literal command walkthroughs in disposable projects. Installation walkthroughs execute pack Python/shell tooling, not prohibited host CLIs. Claims about unobserved host interaction remain marked unverified. The shared prompt covers installation, optional pinned BMad, approved setup, eval-first sign-off and first-lap proposal.

**Failure/recovery:** broken links, inaccurate instructions, missing font licenses, stale generated images and examples that imply unperformed runs block their acceptance. Correct sources and regenerate assets; preserve the distinction between synthetic and actual evidence.

**Checkpoint:** retain the existing story order 29 → 30 → 31 → 32. Draft copy may begin earlier, but final publication claims depend on actual capabilities and evidence. The owner reviews the public release candidate before outward-facing actions.

## Workstream 7 — release and verified publication, story 33

**Outcome:** the intended public repository, v0.1.0 artifacts and hosted showcase are reachable, reproducible and honest about verified behavior.

**Acceptance and proof:** all prerequisite milestones have required evidence and actual human acceptance; full static gate passes; tracked tree, generated release output, history and commit messages pass public-clean review. Build the release archive and checksum manifest from the intended release revision; clean extraction/installation succeeds and tampered payloads fail before execution. After explicit publication GO and maintainer-controlled integration, confirm repository visibility, release/tag identity, checksums, Pages deployment and live site behavior. Capture actual live URLs and deployed revision. Complete or clearly hand off the platform's social-preview manual action.

**Policy precedence:** never push directly to `main`, force-push, commit `dist/`, silently rewrite history or post announcements. Historical launch instructions cannot override these repository boundaries. Publication is prepared fully before requesting its final scoped GO.

**Failure/recovery:** reconcile remote state after unknown push/release/deploy outcomes; do not retry blindly. A failed release or deployment stays failed with receipts preserved. Propose a correction or rollback and obtain any additional authority it requires. Do not move tags to conceal a failed artifact.

**Checkpoint:** publication requires a separate explicit owner GO before outward-facing actions; final acceptance follows observed live proof, not the act of uploading.

## Resolved direction and remaining decisions

The owner clarified continuous execution through existing coding harnesses, visible contributions, risk-based escalation and authorized monitoring. Implement that portable eleven-skill product and the explicitly requested derived graph. Retain the original story dependencies, twenty-question onboarding and epic acceptance. Current candidate-revision disposable-consumer installation checks are real implementation proof; completion-phase equivalence remains a separate decision.

The owner approved SHA-bound passing evidence, independent review and source-linked required checkpoint decisions before new built/done transitions (ADR 0023). Preserve historical records and independently prove the boundary cases if approved. These are structural checks and provenance requirements, without claims of local caller authentication. Final publication still requires its scoped GO.

State-machine/concurrency/gate rules and publication authority are reserved decisions in the repository risk policy. The transition implementation is now authorized; final publication still requires its separate scoped decision. ADR 0024 approves portable source discovery plus self-contained generated native marketplace release artifacts, reconciling the older clean-checkout placement expectation with the no-committed-projections rule.

## Completion report contract

Report implemented, tested, independently reviewed, integrated, staged/deployed and manually accepted as separate facts, with links to actual subjects and receipts. List skipped or unavailable verification explicitly. This proposal records intended acceptance checks; none is claimed to have been run by drafting it.
