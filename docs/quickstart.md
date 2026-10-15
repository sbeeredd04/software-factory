# Start a local factory lap

Use a trusted local Software Factory checkout and an existing consumer project.
Local helpers require Python3.11+ and POSIX locking/no-follow filesystem APIs.
Git is needed for an owned delivery lap. Begin with one host and one small outcome.

## Preview and install

Replace the quoted paths first; do not paste angle-bracket placeholders into a shell.
`pwd -P` records the physical paths used by safe file checks.

```sh
cd '/absolute/path/to/consumer-project'
SF_PROJECT="$(pwd -P)"
cd '/absolute/path/to/trusted/software-factory'
SF_PACK="$(pwd -P)"
SF_HOST='codex'
SF_PYTHON='python3'
SF_REVIEW="$(mktemp -d /tmp/software-factory-review.XXXXXX)"
SF_REVIEW="$(cd "$SF_REVIEW" && pwd -P)"
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad --dry-run
```

Choose `claude-code`, `cursor` or `codex`. Expected: a destination plan ending in
`no changes written`. A conflict is a reason to inspect existing bytes. After
review under the applicable local GO, apply that same plan:

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad
```

This installs project assets and ownership; it does not start agents or configure
service access. BMad provisioning is skipped for this installer smoke route. A
full BMad-planned delivery lap needs observed planner availability and structured planning sources;
missing capability stays a readiness gap. See [installation](installation.md)
for profiles, optional provisioning and preservation.

Keep the private review directory outside the consumer while comparing proposal
bytes, observations and decisions. Remove only that directory after its evidence
retention needs have been reconciled; never remove an unknown path.

## Ground the project

In the actual host UI, invoke `/software-factory` in Claude Code/Cursor or
`$software-factory` in Codex. These are prompts, not terminal commands. The shared
[setup prompt](copy-prompt.txt) describes the intended first lap.

The host reads the repository and existing principles, confirms reusable facts,
and presents a concrete sf-help proposal. Accept safe delegated defaults together;
resolve only material unknowns. Setup applies missing files bound to the exact
reviewed digest and preserves prior documents and answers. An existing repository
may first need the derived sf-crawl artifact. Follow [onboarding](onboarding.md).

## Make one outcome reviewable

Choose a small behavior, its negative case and the existing behavior to preserve.
Establish its actual acceptance/eval decision before implementation. The host
staffs bounded work, tests, reviews, repairs and continues within scope. BMad
skills and their structured epics/stories are the primary planning route.
If the planner is unavailable, record that gap and use only an explicitly scoped
alternative with equivalent review and evidence. Optional accounts and tools
can remain unknown.

A setup draft is not approved delivery readiness. Actual integration/effect proof
and any reserved owner decision or evidence-bound delegated epic acceptance
remain separate. [Verification](verification.md) explains
those boundaries; [smoke-test](smoke-test.md) provides local command observations.
