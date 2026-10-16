# A local smoke walkthrough


Use a disposable consumer for newcomer tests. Keep real user projects and primary
runtime out of fixture mutation. Start with the physical path/host/Python variables
in [quickstart](quickstart.md), plus an existing private review directory outside
the consumer. Keep preexisting README/convention/settings sentinel hashes for
comparison. A changed user sentinel is a failure to investigate, not a reset step.

## Preview, apply and repeat

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad --dry-run
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad
```

Observe the dry-run's no-write result, first ownership publication, zero-change
repeat and preserved sentinels. Do not use allow-overwrite to make this test pass.
Choose installed helper paths:

```sh
case "$SF_HOST" in
  claude-code) SF_SKILLS="$SF_PROJECT/.claude/skills" ;;
  cursor|codex) SF_SKILLS="$SF_PROJECT/.agents/skills" ;;
esac
SF_KERNEL="$SF_SKILLS/software-factory/scripts"
```

## Discover and review setup

```sh
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-help/scripts/discover.py" --project "$SF_PROJECT" --json > "$SF_REVIEW/discovery.json"
```

For an existing repository that lacks config/CODEBASE, create the owned derived
crawl artifact before proposal; this step writes it, without executing source:

```sh
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-crawl/scripts/crawl.py" "$SF_PROJECT" --artifact "$SF_PROJECT/.software-factory/context/CODEBASE.md" --json "$SF_REVIEW/crawl.json"
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-help/scripts/setup.py" propose --project "$SF_PROJECT" > "$SF_REVIEW/setup-proposal.json"
```

Review missing-file drafts, preserved facts, twenty answer slots, unknowns and
proposal digest. Real consumer apply needs the exact reviewed digest/source ref
under applicable GO; see [onboarding](onboarding.md). A fixture uses explicitly
synthetic decision/answer data and must not claim independent owner signoff.
After actual approved setup, validate and observe:

```sh
"$SF_PYTHON" -I -B "$SF_KERNEL/config.py" validate --config "$SF_PROJECT/.software-factory/config.yaml" --root "$SF_PROJECT"
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-agents/scripts/agents.py" --project "$SF_PROJECT" discover
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-evolve/scripts/evolve.py" registry --root "$SF_PROJECT"
```

Expected: valid actual references; optional native/external availability may remain
unknown, registries may be empty and nothing connects/executes automatically.
A repeat setup can report reuse, preserving answers rather than new approval.
Tampered/stale/partial proposals refuse without destructive cleanup.

## Provider-free doctor fixture

Unrestricted doctor can run available `gh auth status`. For a deterministic
fixture, create only this explicit shadow in the private review directory:

```sh
mkdir -p "$SF_REVIEW/offline-bin"
cat > "$SF_REVIEW/offline-bin/gh" <<'SH'
#!/bin/sh
printf '%s\n' 'documentation fixture: authentication deliberately unverified' >&2
exit 1
SH
chmod 755 "$SF_REVIEW/offline-bin/gh"
PATH="$SF_REVIEW/offline-bin:$PATH" "$SF_PYTHON" -I -B "$SF_PACK/install.py" doctor --project "$SF_PROJECT" --json > "$SF_REVIEW/doctor-offline-fixture.json"
```

Observe actual checks and preserve their statuses. This auth result is simulated/
unverified, not a real account check. Newcomer tests also guard forbidden host
CLIs and compare consumer/source/home snapshots. Doctor can exercise verified
hooks in a disposable fixture; blocked results are nonzero, warnings are not a
blanket failure. Remove no user files to manufacture green.

## Read recovery facts and preview removal

When a run/board actually exists, the orchestrator reads `state.py status` and
`reconcile` plus `trace.py query ready` with `--workspace "$SF_PROJECT"`, and
compares actual Git HEAD/diffs. No run yet is a truthful prerequisite gap.
Checkpoint writes and board refresh belong to their existing owners; neither is
an implicit dispatch or acceptance. See the canonical
[recovery contract](../skills/software-factory/references/recovery.md).

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" uninstall --project "$SF_PROJECT" --host "$SF_HOST" --dry-run
```

Observe a no-write removal/preservation plan. Retain config/context, evidence,
overlays, BMad and edited user content according to the lifecycle contract.
Finish with actual commands/exits/subjects, meaningful failed/unknown results and
one next action. This local walkthrough is not browser, remote CI, deployment,
production monitoring, signed consumer acceptance or applicable epic-decision proof.
