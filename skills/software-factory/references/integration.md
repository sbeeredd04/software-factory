# Integration and deploy proof

Phase: integration — merging proven work and proving it where it runs.

## One integration owner

The orchestrator is the single integration owner. Independent tracks build, test
and review concurrently, but merges to the configured integration branch happen
sequentially, one owner, after the gates pass. The approved GO scopes what may
be committed, pushed and merged; that authority extends to the integration
branch and nowhere else.

Before merging, inspect the actual branch, base, status, diff and untracked
paths, and match changed paths to the story and the current claims. Stage
explicit paths, review the staged diff for secrets and unintended changes, and
commit conventionally with the repository's configured identity. Use the
repository's standard merge method and branch protection.

Read the actual review-bot threads and their dispositions at merge time: a
missing or skipped required check is blocked, not passed, and any approved
narrower applicability stays linked to its scoped decision. Record PR, head SHA,
CI and bot receipts. An unknown network outcome — a push, merge or API call
whose result was not observed — is reconciled against the provider's actual
state before any retry.

## Rebases and combined proof

Check dependency and base changes, claims, compatibility and shared-resource
pins. After a base moves, rebase and retest the affected stories only; do not
restart unaffected workers. The required checks still run on the combined merge
SHA — per-story proof does not cover the integrated result.

## Deploy proof

A merge is not a deploy. Read the live target environment: which branch it
tracks, which SHA it serves, its health and the affected behavior. Written
answers about tracked branches go stale; inspect the live state. Then exercise
the affected flow on the deployed SHA. A health-check 200 is reachability, not
proof. A manual deploy to a shared environment is a separate scoped action, not
an inferred consequence of a merge.

Failed or unknown deploy proof returns to the work loop, with receipts preserved
and the affected retest scope named. Work that cannot be deployed carries an
approved, recorded narrower applicability instead of a silent exemption.

## Closing

Record the PR, merge, deployment and effect receipts. Release reconciled claims
when safe, checkpoint, and update the story's board record and its planning
source after merge and deploy proof.
Keep epic acceptance pending until the policy-selected actor completes the
current evidence/authority checks in [authority](authority.md); independent eligible
work continues. Reports distinguish implemented, tested, merged, deployed and
accepted (with the actual actor and mode) — five separate
states, never collapsed into "done".
