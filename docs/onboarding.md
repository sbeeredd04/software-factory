# Onboarding a project

Install the pack with the project installer, then ask `sf-help` to set up the
factory for your intended outcome. Portable skill discovery alone is skills-only;
full setup needs the installer's template and schema projections.

Onboarding reads existing context and pre-fills twenty decision slots in five
groups. It reuses confirmed answers; you can accept safe defaults in one action
or say “you decide.” Only unresolved material questions need a prompt. Existing
configuration, principles and planning remain intact.

The host presents exact missing-file drafts and their proposal digest before any
consumer write. Approval applies that concrete local setup. New proposals select
BMad planning, risk-adaptive mode, local edits/commits within GO and no automatic
manual epic stop; external flags remain false. Existing profiles are preserved.
Optional BMad provisioning, review bots, external access and monitoring have
separate scoped decisions. BMad skills and structured epics/stories are the primary planning route.
If unavailable, the host records a readiness gap and reconciles a scoped
alternative before claiming a completed planning phase.

The deterministic helpers provide bounded read-only discovery, proposal creation
and create-only approved application. They do not establish model availability,
CI success, real owner identity, live monitoring or delivery readiness. The setup
receipt records provenance and unknowns; board and run evidence keep their existing
authority. Partial or stale setup stops for reconciliation rather than overwriting.

After setup, the host proposes one small real story and continues the approved
build/test/review/repair/ship loop. Monitoring uses actual authorized host tools;
this Markdown and standard-library pack does not supply a background service.

With the [quickstart variables and installed helper paths](quickstart.md#preview-and-install)
established in the same shell, discover first:

```sh
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-help/scripts/discover.py" --project "$SF_PROJECT" --json
```

For an existing unconfigured repository, [the smoke walkthrough](smoke-test.md) shows the derived crawl and `setup.py propose` commands. Inspect exact drafts and digest before the host applies a real source-linked decision. `setup.py apply --approve-sha` checks reviewed bytes and current root; the digest is provenance, not authentication.
