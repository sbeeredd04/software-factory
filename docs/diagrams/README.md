# Workflow diagrams

Each of the nine Mermaid sources has a rendered SVG beside it and a prose
equivalent below. The sources are the canonical diagram interface for the README.
Local rendering verifies syntax and image production; it does not establish
GitHub rendering or live host behavior.

## Hero loop

Source: [hero-loop.mmd](hero-loop.mmd); rendered image: [hero-loop.svg](hero-loop.svg).
Ground intent and existing facts; use observed BMad skills and structured
stories to plan and review within scoped GO. The active host staffs claimed work, then workers
implement and independently verify. Failed or unknown proof returns to work.
One integration owner checks the combined SHA; affected behavior must be proved
on the resulting artifact. Escalate material risk or a reserved owner decision
with its real source and scope.
Otherwise continue the evidence-bound acceptance and next eligible priority.
This compact loop is suitable for the README first screen; details follow below.

Canonical detail: [entry](../../skills/software-factory/SKILL.md),
[feature workflow](../../skills/software-factory/workflows/feature.md),
[authority](../../skills/software-factory/references/authority.md).

## Feature loop

Source: [feature-loop.mmd](feature-loop.mmd); rendered image: [feature-loop.svg](feature-loop.svg). Ground the outcome in actual project
facts. Observed pinned BMad skills and structured epics/stories produce a
risk-sized plan for independent review. Reuse applicable GO; a material missing
decision blocks its dependents while independent approved work continues. Claim
eligible paths before implementation. Actual-HEAD QA/evals and actual-diff review
return failed, unknown or confirmed findings to repair. Check in receipts while
ownership is held, reconcile the handoff, then release. All providers must be done
for built, even though review may unlock starting a successor. One owner integrates
under approved branch scope and checks the combined SHA. Authorized staging or an
approved local equivalent proves the affected behavior. Story completion and applicable evidence-bound epic acceptance are distinct;
reserved human decisions remain binding. Continue the eligible frontier.

Canonical detail: [feature](../../skills/software-factory/workflows/feature.md),
[integration](../../skills/software-factory/references/integration.md),
[protected transitions](../../skills/software-factory/references/evidence.md#protected-board-transitions).

## Bug loop

Source: [bug-loop.mmd](bug-loop.mmd); rendered image: [bug-loop.svg](bug-loop.svg). A report, eval failure or authorized signal
gets a durable identity, primary evidence and safe reproduction. Keep mechanism
separate from hypothesis. Unknown cause requires a separating experiment or one
focused clarification. Demonstrably correct or already-handled behavior closes
only after independent reproduction and disposition review supports that conclusion.
An unconfirmed or disputed conclusion returns to evidence. Supported no-fix closure
changes zero code; it is not a manufactured implementation, merge, passing
fail-to-pass case, delivered story or implicit cancellation decision.
A confirmed in-scope defect receives a reviewed plan and regression/eval cases,
claimed repair, independent proof, actual-diff review and gated integration.
The original reproduction must pass on the resulting artifact; failed or unknown
outcomes reopen repair. Close with evidence and assess applicable acceptance and escalation.
Re-observe only within authorized access/window. A recurrence after terminal
closure creates a linked follow-up; it does not rewrite the closed record.

Canonical detail: [bug](../../skills/software-factory/workflows/bug.md),
[operations](../../skills/software-factory/references/operations.md).

## Install flow

Source: [install-flow.mmd](install-flow.mmd); rendered image: [install-flow.svg](install-flow.svg). Start from a trusted pack revision,
physical consumer root and chosen host. Preview the full or skills-only project
profile, inspect ownership/collisions and preserve user files. Installation uses
the existing lock, captured source revalidation, conditional publication and
ownership manifest; conflicts or concurrent edits refuse safely. Inspect the
actual output and unchanged repeat. A separately consented pinned official BMad
installation has its own prerequisites, output checks and degraded/partial
outcomes; no implicit retry is promised. Skip-BMad is an installer smoke route; full planning readiness remains
unverified until an actual BMad planner or scoped equivalent is observed.
Doctor reports observations/unknowns and can run available `gh auth status`;
read-only does not mean provider-free. Preview uninstall first; an authorized
uninstall handles selected owned files and preserves edits and user context.
Native bundles and raw portable skills are separate routes with their documented
asset limitations, not interchangeable claims about this project profile.

Canonical detail: [installer](../../install.py),
[distribution](../distribution.md),
[BMad provisioning](../../scripts/bmad_install.py).

## Host projection

Source: [host-projection.mmd](host-projection.mmd); rendered image: [host-projection.svg](host-projection.svg). Canonical skills, role prompts,
host policies and required auxiliary assets feed project installation or the
allowlisted native bundle generator. Their generated Claude Code, Cursor and
Codex layouts supply instructions to the active host. That host owns orchestration,
staffing, actual permissions/model availability and dispatch under applicable GO.
Local helpers validate, record and project bounded facts; registry/routing output
is a proposal, not an executor or a grant of rights. Static layout checks show
format evidence; they do not demonstrate live loading, supported host capacity,
provider authentication or a particular effective model. The eleven roles are
available tools, not a mandatory fleet.

Canonical detail: [team](../../skills/software-factory/references/team.md),
[agent skill](../../skills/sf-agents/SKILL.md),
[distribution](../distribution.md).

## Onboarding

Source: [onboarding.mmd](onboarding.mmd); rendered image: [onboarding.svg](onboarding.svg). Inspect real intent/documents, with a
bounded crawl for an existing ungrounded repo, then read-only setup discovery.
Exactly twenty catalog slots organize reused facts and confirmed answers; they
are not twenty mandatory new prompts. Ask only for material unknowns, and offer
safe defaults in one action. Review the exact missing-document/config proposal,
source digest and unknowns; the host reconciles real GO and its source before
exact create-only apply. Stale inputs, collisions, root changes and partial state
must preserve existing bytes and report a safe next action. Validate actual
config and chosen documents. Re-onboarding reuses answers without claiming a
new approval. A real consumer eval signoff precedes its queue; example signoffs
supply no authority. Optional access remains unknown until actually established.

Canonical detail: [help](../../skills/sf-help/SKILL.md),
[setup helper](../../skills/sf-help/scripts/setup.py),
[configuration](../../skills/software-factory/references/configuration.md).

## Evolve loop

Source: [evolve-loop.mmd](evolve-loop.mmd); rendered image: [evolve-loop.svg](evolve-loop.svg). Begin with observed rework, principles,
current revision and applicable GO. Read-only local capability metadata needs
adequate identity, license, digest and permission facts; unknown adoption can
wait while native work continues. Inspect actual pinned BMad customization and
callback recursion, or capture an overlay's exact generated base/payload/evidence.
Review the smallest proposal independently with real regression/canary artifacts.
The host reconciles authority; material trust, governing-policy or external-effect
changes need a named human source decision. For a supported Markdown overlay, the existing installer alone owns
composition/publication; drift or edited targets require a new reviewed proposal,
not an overwrite escape. Capability or MCP adoption instead requires an actual
scoped host/tool action and observed availability; the registry neither installs
nor connects. Unavailable or unproved adoption remains proposed/unknown while
native work continues. BMad customization uses its actual supported host method
under the reconciled scope. Inspect each actual result, applicable ownership and
an authorized later run. Retain an improvement with evidence, or propose a scoped
rollback and prove restored behavior. Helpers install no capability, connect no
MCP, grant no permission and create no daemon.

Canonical detail: [evolve](../../skills/sf-evolve/SKILL.md),
[overlays](../../skills/sf-evolve/references/overlays.md),
[retro](../../skills/sf-evolve/references/retro.md),
[registry](../../skills/sf-evolve/references/registry.md).

## Eval flow

Source: [eval-flow.mmd](eval-flow.mmd); rendered image: [eval-flow.svg](eval-flow.svg). Ground stable fail-to-pass and pass-to-pass
cases in the relevant requirements, risk and surfaces. An actual approved plan
and bound signoff precede covered work. Run actual cases on identified subjects;
missing harness/access/proof remains unverified or blocked. Keep real output,
artifacts and verdicts. Failed, stale, tampered or unknown proof returns to triage
and repair without erasing prior failures. Independent evidence review and the
applicable strict board gate precede integration; combined-SHA proof and affected
artifact effects remain separate. An exceptional override requires an actual
scoped source decision and preserves the original case/verdict history. Hashes
establish structural integrity, not authenticated identity or live effect truth.

Canonical detail: [eval skill](../../skills/sf-eval/SKILL.md),
[evidence](../../skills/software-factory/references/evidence.md).

## Board and roadmap

Source: [board-roadmap.mmd](board-roadmap.mmd); rendered image: [board-roadmap.svg](board-roadmap.svg). The owner derives immutable IDs
from stable planning-source keys. Per-story records are the only live story-status
authority. Readiness uses dependency edges and applicable accepted epic gates, with explicit
order used for ranking. A prerequisite in `in-review`, `built` or `done` can
unlock starting a dependent; built
requires all its providers done and strict premerge proof. Workers claim paths
before in-progress and check in receipts/in-review before releasing a reconciled
handoff. Actual merge and merge-subject evidence gate done. All children done or cancelled only makes the epic eligible for acceptance;
record evidence-bound delegated or reserved human provenance as applicable.
A blocked overlay preserves the underlying status. Scoped confirmed cancellation
is terminal, and cancelled prerequisites continue blocking until explicit
reconciliation. Independent eligible work continues across pending checkpoints.
The owner regenerates timestamped roadmap/dashboard/graph views from records and
existing kernel claims/checkpoints. These views and attribution reports are not
a second status store, proof that a worker runs, or verified external shipping.
Status-only reads do not regenerate projections or dispatch workers.

Canonical detail: [recovery and board contract](../../skills/software-factory/references/recovery.md),
[trace](../../skills/software-factory/scripts/trace.py),
[roadmap](../../skills/software-factory/scripts/roadmap.py) (`MET_STATUSES`,
`unmet_dependencies` and its stricter `for_merge` branch).

## Validation

Check each source against the final canonical contracts, locally render all nine,
retain SVGs and the adjacent prose equivalents, run link/public-scan/document tests and the
required full gate on an exact committed subject. Keep README blocks equal to
these nine sources, and retain the renderer output and exit status.
