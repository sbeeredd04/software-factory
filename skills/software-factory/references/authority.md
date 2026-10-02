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
authorized each program in the checkpoint notes.

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
only its dependents; independent safe work continues.

## Uncertain outcomes

Authority includes the duty to reconcile: when the outcome of an external action
is unknown — a push, merge, deploy or purchase whose result was not observed —
inspect the provider's actual state before retrying. Retrying an action whose
first attempt may have succeeded is how duplicated side effects happen.
