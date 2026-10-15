# Installation and safe removal


Start with the physical-path variables in [quickstart](quickstart.md). Python3.11+
and POSIX descriptor/locking APIs are required by the local helpers. Current
execution evidence is macOS/Python3.12; native Windows and other platform execution
must not be inferred from portable Markdown or configured CI jobs.

## Profiles and preservation

The default `full` project profile supplies skills, auxiliary schemas/templates,
roles, host hooks/pointers and runtime helpers. In a fresh separate consumer:

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad --dry-run
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile full --skip-bmad
```

A project skills-only installation uses the same owner and auxiliary skill assets,
but omits full-profile roles/hooks/runtime/pointers:

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" install --host "$SF_HOST" --project "$SF_PROJECT" --profile skills-only --skip-bmad --dry-run
```

Review before omitting `--dry-run`. A profile change over a previous full install
is not proof that old full-profile files were removed. Raw skills-discovery
acquisition supplies a portable skill route with its stated dependency/setup
limits. Native marketplace generation produces static artifacts, not enabled
host registration. See [distribution](distribution.md); avoid stacking project
and plugin installs for the same host.

## Repeat, upgrade and conflicts

Repeat the ordinary reviewed install from the trusted checkout. Identical inputs
should report zero changes. Changed source yields a new plan; inspect it before
applying. The installer tracks hashes, ownership and original restoration bytes.
It preserves unrelated merge content and refuses edited owned or unowned conflicts.

An explicit repeatable `--allow-overwrite PATH` authorizes one reviewed conflicting
repo-relative path and records a private backup. It is not a default repair and
cannot force an overlay conflict. Preserve evidence, reconcile current bytes and
use the [evolution contract](evolve.md) for reviewed persistent customizations.

## Optional BMad

The local installer smoke uses `--skip-bmad`. A BMad-planned delivery lap
requires observed provisioning and planning capability. Separately consented provisioning
omits that flag and uses the canonical pinned official installer. It needs
Node>=20.12 plus node/npm/npx/uv/git and may acquire upstream content. Missing
prerequisites degrade truthfully; existing/partial trees remain preserved.
No implicit upgrade/retry or generated-workflow execution is established. Missing
BMad is a named planning-readiness gap; do not claim a BMad plan was produced.
See the [BMad setup](bmad.md) and canonical [BMad guidance](../skills/sf-evolve/references/bmad.md).

## Doctor and removal

```sh
"$SF_PYTHON" -I -B "$SF_PACK/install.py" doctor --project "$SF_PROJECT" --json
"$SF_PYTHON" -I -B "$SF_PACK/install.py" uninstall --project "$SF_PROJECT" --host "$SF_HOST" --dry-run
```

Doctor does not alter project/source files, but can run available `gh auth status`,
local Git and verified hooks in disposable fixtures. It is not a blanket offline
command; [smoke-test](smoke-test.md) gives a labeled fixture override. Optional
unknowns do not establish access; blocked checks cause nonzero status.

Uninstall dry-run writes nothing. Inspect preserved edited files and selected
hosts before any actual removal. Config/context, overlays/evidence, BMad and
backups have their own preservation contracts. Selective removal retains the
other host's shared assets; it is not a remote account or service cleanup.
