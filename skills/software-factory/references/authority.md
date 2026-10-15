# Authority and escalation

Phase: authority — deciding what may proceed without asking, and how to ask.

The entry's **Hard boundaries** block is the single statement of the limits;
this reference does not restate them. What follows is how delegated authority
works inside those limits.

## Delegated authority

Work proceeds under an approved GO: a scoped go-ahead from the human owner. A GO
names its scope — the outcome, the stories or areas it covers, and the actions
it authorizes (typically: edit and commit in story worktrees, push story
branches, open pull requests targeting the integration branch, and merge to the
integration branch after the gates pass). Authority never silently extends past
its scope: a GO for one epic is not a GO for the next, and approval to merge to
the integration branch is not approval to touch a protected branch or any
production system.

Reuse an existing GO whenever the request fits its scope. Record which GO
authorized each program in the checkpoint notes. Within that scope the
orchestrator owns continuous execution: choose ready work, dispatch and wait,
verify independently, repair or recover, and refill available capacity without
asking for another prompt at each step. Status updates do not consume or renew
authority. A status-only request retains the entry's read-only behavior.

The [feature](../workflows/feature.md) and [bug](../workflows/bug.md) loops own
delivery: understand and prioritize needs, plan, staff, build, test, review and
ship under the applicable authority. [Operations](operations.md) owns authorized
observation, signal triage and continued priorities within GO, including the
source/access/window boundary. New monitoring configuration, credentials or
schedules require their own scoped authority.

## Autonomy defaults

Configuration can tune the defaults (`autonomy` in
[configuration](configuration.md)): local edits and commits sit within the
request; push, open-PR, merge and deploy default to ask. A standing delegation
removes repetitive questions only inside its exact recorded scope. Test
credentials, sandbox accounts and staging access are never permission for real
external side effects — purchases, messages, bookings or any irreversible action
stay with the human unless explicitly delegated for that exact action.

## How to escalate

Bring principle conflicts, new scope, new authority and real risk to the human
owner as exactly one focused question carrying a recommendation and 2-4 options.
Record the answer durably (checkpoint decisions, plus the principles or decision
documents when the human changes them) and honor it. A pending question blocks
only its dependents; independent safe work continues, unless the owner selected
`stop-and-ask`. Explicit human reservations remain binding; closing stories alone
does not accept their epic.

## Uncertain outcomes

Authority includes the duty to reconcile: when the outcome of an external action
is unknown — a push, merge, deploy or purchase whose result was not observed —
inspect the provider's actual state before retrying. Retrying an action whose
first attempt may have succeeded is how duplicated side effects happen.

## Consequence assessment at every phase

Reassess on new intent, findings, scope or access, before consequential actions,
at integration/effect proof, during recovery and at acceptance. Record the cause
and intended outcome; affected behavior, data, files, branches, environments,
tenants, trust, money and external systems; proposed method and actual permissions;
effect proof, recovery, reversibility and blast radius; governing owner scope,
autonomy and reservations; unknowns and the decision with rationale.

Choose proceed within scope, deepen independent review/proof, or escalate. Record
exact blocked dependents and the required owner action. Preserve prior assessments
and failures. A risky module name alone does not force another question: reversible
local auth-parser tests or transaction repairs can proceed within a covering GO
with suitable independent review. New trust/credential scope, irreversible data
operations, material product tradeoffs, consequential production effects and
unbounded recovery need applicable owner authority. Existing project reservations
remain in force until explicitly amended. No risk score overrides them.

## Conditional epic acceptance

`autonomy.mode` is `supervised` or `risk-adaptive`; absence preserves legacy
supervised acceptance. New setup proposes risk-adaptive, local edits/commits within
GO and `checkpoints.manual: false`; external flags stay false. Existing profiles
are preserved. Durable checkpoints still occur at configured transitions/reset/
external writes. Persisting a checkpoint and asking a human are separate actions.
A manual profile, epic `hitl: true`, unresolved required story checkpoint or an
applicable project reservation keeps human acceptance mandatory. The helper treats
manual true conservatively for epic acceptance, including custom transition lists.

Under adaptive policy, a current finite owner grant can delegate acceptance for
named epics. Mode alone grants nothing. The protected helper requires the same
child/effect checks and independent reconciliation for both actors, plus current
authority and consequence bindings for the orchestrator. The accepting owner and
reviewer must differ from every implementation owner. Legacy descendants require
explicit scoped legacy authority and independent reconciliation, never fabricated
gates. See [evidence](evidence.md) for the concrete source/assessment contract.

An orchestrator acceptance records its actual identity and `mode: delegated`;
it never uses the human actor or a fabricated human decision. The host verifies
actual owner identity, permissions and the truth of consequences. Helpers check
bounded assertions, digests and source provenance; they cannot authenticate a
caller or prove the reasoning. Accepted epic `done` unlocks dependencies; waiting
for acceptance can mean evidence/authority reconciliation or a reserved human choice.
