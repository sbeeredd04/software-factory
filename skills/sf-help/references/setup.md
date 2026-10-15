# Approved setup and recovery

## Prepare the concrete proposal

Read the existing crawl, discovery and the [question catalog](questions.md).
Reuse prior confirmed answers; record each of twenty slots as `confirmed`,
`defaulted` or `unknown`, with a bounded value and source reference. Confirm known
answers in one line rather than re-interviewing. Accept-all-defaults or “you decide”
selects safe local defaults; unknown authority and capability remain unknown.

Use the canonical `templates/PRINCIPLES.md`, `templates/ARCHITECTURE.md` and
`templates/CONVENTIONS.md`, projected into installed `sf-help/templates/`.
Principles become four modules: product, conventions, risk and evals under
`.software-factory/context/principles/`. Existing conventional architecture and
conventions are referenced and preserved. Host-ground the drafts with the actual
outcome, stack, invariants, design bar and source anchors before approval.

```sh
python3 scripts/setup.py propose --project PROJECT
```

Output goes to stdout, never directly into the consumer project. Save it in an
explicitly chosen review artifact outside the consumer when needed. `--answers`
accepts a JSON object with twenty ordered `answers` records (`id`, `state`, `value`,
`source`); `--config-draft` accepts the actual proposed config. `--document-drafts`
accepts a JSON `files` map of proposed missing Markdown paths to grounded content.
Use this to replace generic scaffolds before approval; existing documents are
preserved. These are inputs,
not permission. The proposal contains exact output bytes, input digests, directory
identity, all twenty answers, outstanding slots and its own SHA-256 digest.
Use canonical physical paths for helpers and input artifacts: resolve temporary
directory aliases first. The config reader deliberately rejects symlink traversal;
do not weaken that policy to accommodate an aliased temporary path.
Prefilled answers include actual config paths and observed commands/bot/document
facts. Answer prose does not change configuration automatically: the host maps
changed answers into the explicit config/document draft and reviews both together.
With a custom config, only its selected missing canonical document paths are
proposed. Unreferenced generic conventions, tracker and eval scaffolds are omitted;
existing linked principles and eval plans remain the selected sources.

Defaults include risk-adaptive mode, local edits/commits within GO, manual false,
BMad planning and native worker fallback, alarm budgets, optional owner ceiling omitted,
empty bots/environments, disabled monitoring and external writes. These are setup
choices, not observed capabilities. All mappings use the strict configuration
contract; qualitative policy stays in documents. A new `evals-draft.json` is
explicitly a draft, not a runnable approved eval plan. `sf-eval` authors actual
cases, commands and signoff before delivery GO. Never reuse Shopfront's synthetic
approval or report schema validation as runnable proof.

The helper validates syntax, schema and required documents through captured and
proposed bytes. Run the installed config validator after apply as an additional
check. Optional standard JSON Schema crosschecks are separate; absence is a skip.

## Approval boundaries

Present changes, preserved files, defaults, conflicts and unknowns before asking
for approval. An answer conflicting with observed conventions needs a concrete
recommendation and owner decision; never silently resolve it. Approval may cover
all concrete local setup files at once. It does not cover bot generation, network
installers, credentials, paid tasks, publication, deployment or monitoring access.

```sh
python3 scripts/setup.py apply --project PROJECT --proposal REVIEWED_JSON \
  --approve-sha REVIEWED_SHA256 --decision-ref OWNER_DECISION_SOURCE
```

The host verifies the real source-linked owner decision. CLI flags provide
structural integrity and provenance only; they cannot authenticate a human.
Application validates the actual config bytes and creates missing approved files
only, with exclusive publication and
no overwrite. Each file is individually atomic; the whole set is not a filesystem
transaction. The bounded `.software-factory/setup-receipt.json` is written last,
recording twenty answers, config path/digest, discovery sources, outstanding slots,
written file hashes and approval reference. It is setup evidence, not live status.
No active program pointer, tracker status or board record is created here.
Root identity and input file/directory inventories are rechecked through publication
and final validation, allowing exact setup-owned additions only.

Changed inputs, unsafe paths, output collisions and partial prior applications
are rejected. Preserve partial bytes; compare against the proposal, reconcile
manually under a specific decision, then prepare a new proposal. Do not delete or
retry blindly. The same complete approved proposal is an unchanged no-op only
while other inputs still match. A final concurrent change can leave a receipt
requiring reconciliation; an error or stale receipt is not current setup proof.
Re-onboarding preserves existing config/docs/confirmed answers. A changed config
or changed prior answers needs an explicitly reviewed amendment; this create-only
helper does not overwrite setup history. Existing valid configuration without a
receipt can adopt an approved evidence receipt without rewriting the config.
Existing enabled monitoring declarations are preserved byte-for-byte; they do not
prove live access or grant new authority. Re-onboarding returns prior answers and
fresh discovery separately, without presenting old approval as current permission.

## Optional integrations

For selected review bots, route an approved rendering proposal to `sf-agents`.
Zero bots is a first-class no-op. Preserve existing user sections and verify actual
current-subject reports later; configuring a bot is not a successful review.

BMad present or partial: preserve and reuse; observe version, modules, host coverage
and planning model (v6 sprint-status vs v7 ticket tree) when evidence supports them.
Unknown fields stay unknown. Never reinstall over `_bmad/`, manifests, lockfiles or
existing host skill directories. Absent BMad: offer the project installer's pinned
optional route, with consent before npm network access and upstream code execution:
`bmad-method@6.12.0`, modules `bmm,bmb,cis,tea`, `--yes`,
`--pin tea=v1.27.2 --pin bmb=v2.2.2 --pin cis=v0.3.2`.
Use the canonical provisioning reference for the complete installer contract;
`--yes` selects upstream defaults, not blanket authority. Decline, missing
prerequisites or failure is an explicit BMad planning gap. Native requires an
owner-selected method, scoped fallback decision or existing approved legacy route;
label actual method honestly. No GO without a concrete minimal spec, acceptance
and eval readiness. No hidden
network call, trust configuration or service is part of this setup helper.

## Operational handoff

Monitoring remains disabled until the host confirms actual support and the owner
approves each source, read scope, observation window/cadence/end condition, trigger,
deduplication, data-policy reference, notification destination and repair GO.
Map these through `operations.sources`, `authority_ref`, `until`, `schedule_request`,
`followup` and `notifications`; source-linked authority/trigger documents carry
window/cadence/destination/repair details. Registration is not permission, and
`authorized-repair` grants neither deployment nor rollback.

Unknown capability, missing auth, empty/partial data and unknown deployed identity
stay explicit; none means healthy. The host observes only within approved windows,
stops on expiry/revocation, and deduplicates repeated signals against existing
bug/story evidence. Confirmed in-scope failures may enter the existing bug loop
with regression proof; new product scope or production effects require a material
decision. Reconcile unknown external outcomes before retrying. Resume uses durable
source/cursor evidence without claiming a live worker or replaying duplicate bugs.
No helper polls, schedules, sends notifications or maintains another status store.

## Summary and first lap

Close with detected / written / skipped items and reasons, config validation,
remaining unknowns, and the actual source-linked approval. Propose one concrete
real story for this repository with acceptance and a meaningful check, sized to
finish in one session. Greenfield: one chosen skeleton behavior and test. Recommend
a dry run or scratch clone for the first lap in an unfamiliar repo. The helper's
first-lap placeholder is an input to this host planning, never dispatch-ready GO.

Continue under existing user scope through worker, independent reviewer, repair,
next eligible work, integration and effect proof; complete policy-selected epic
acceptance while preserving explicit human reservations.
Offer a design audit once, off by default: `sf-design`, `sf-smell-audit`,
`sf-refactor`, `sf-patterns`. With approval, record file-anchored findings in
`.software-factory/context/design-audit.md`. They feed candidate stories only;
never auto-schedule, auto-apply or merge findings into principles without approval.
