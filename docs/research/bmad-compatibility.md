# BMad external-module compatibility

> Historical experiment and proposal. [ADR 0025](../../.software-factory/context/decisions/0025-bmad-module-compatibility-pins.md) subsequently resolved the module choice: BMad Method 6.12.0 with tea v1.27.2, bmb v2.2.2 and cis v0.3.2 through the official installer. The [current guide](../bmad.md) describes prerequisites and limits. Preserve the failed TEA3 experiment below as a historical observation; successful provisioning does not prove generated workflow quality or live host loading.


Research date: 2026-10-15. These are observed installer results and a proposed
command amendment. They do not record owner approval, live host loading or
successful execution of BMad planning workflows.

## Observed incompatibility

The original pinned BMad 6.12.0 command failed its real network fixture.
Its default external-module selection resolved TEA v3.0.2, whose repository
tree lacks the module definition expected by that installer. The factory
projections survived and the failed upstream outcome was recorded.

The [pinned registry](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/bmad-modules.yaml)
expects TEA's module definition at src/module.yaml. The
[TEA v3.0.2 tree](https://api.github.com/repos/bmad-code-org/bmad-method-test-architecture-enterprise/git/trees/v3.0.2?recursive=1)
has no module.yaml. At investigation time its default branch had the same
source identity; selecting the next channel would not resolve this failure.

## Tested alternatives

An independent product specialist ran two fresh disposable all-host installs
with isolated home/cache, closed stdin and prohibited host CLI guard stubs:

- TEA v1.27.2 alone pinned: exit 0, 8.25 seconds.
- TEA v1.27.2, BMB v2.2.2 and CIS v0.3.2 pinned: exit 0, 9.12 seconds.

Both produced core/BMM 6.12.0, the requested host IDs, and 54 BMad skill
directories in each Claude and shared skills root. Neither attempted a
guarded host CLI invocation. The second run recorded all external channels
as pinned. A preliminary successful run used the operating system's default
temporary directory; it was retained separately, then the two explicit
disposable fixtures above were run.

Observed external source identities:

- BMB v2.2.2: 4a1422274a2acb0fb0ec0511753da6263948f072.
- CIS v0.3.2: 97298b22fee1c7e482710d3a8414adb5cfccccd9.
- TEA v1.27.2: d99ad29c62697c152e3393351406686d5bcd323c.

The reusable experiment and raw outputs remain private investigation
artifacts. This memo records sanitized observations.

## Proposed amendment and limits

Append these arguments to the existing command, retaining its package pin,
host mapping, module set and existing-install preservation:

```text
--pin tea=v1.27.2 --pin bmb=v2.2.2 --pin cis=v0.3.2
```

The [pinned command](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/commands/install.js)
supports repeatable CODE=TAG pins. Its
[channel resolver](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/modules/channel-resolver.js)
and [external manager](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/modules/external-manager.js)
resolve tags; a raw commit hash is not a supported replacement for a tag.

Three explicit tags reduce selection drift. Tags can move and npm transitive
dependencies still resolve independently, so this is not an immutable
dependency lock. Preserve actual resolved versions and source identities.
The experiment establishes installer output only, not generated workflow
quality, runtime trust, monitoring, deployment or acceptance. Upstream printed
optional setup and update instructions; those were not executed.

The owner decides the exact-command amendment before shipped behavior changes.
Retain the original failed test and exploratory proof as distinct outcomes.
