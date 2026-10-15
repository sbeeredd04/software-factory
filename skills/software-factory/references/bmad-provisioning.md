# BMad provisioning

A normal `install.py install` first commits the factory projections, then runs
an independent BMad provisioning phase. `--skip-bmad` bypasses all BMad discovery,
probes and subprocesses. `--dry-run` only describes the factory plan and writes
nothing. BMad is optional: unavailable prerequisites leave the factory usable
with native planning and an explicit degraded report.

## Pinned invocation and prerequisites

Fresh provisioning invokes this argument vector without a shell, with stdin closed:

```text
npx -y bmad-method@6.12.0 install --directory ABSOLUTE_PROJECT_PATH --tools HOST_IDS --modules bmm,bmb,cis,tea --yes --pin tea=v1.27.2 --pin bmb=v2.2.2 --pin cis=v0.3.2
```

Host IDs are `claude-code`, `cursor`, and `codex`; multiple selections use a
comma-separated value. The directory is the actual consumer project. Node must
be at least 20.12; npm/npx must function. Git supports upstream Git sources. uv is
a pack preflight requirement, not a requirement established by BMad's package
metadata. Missing executables cause no version probes. An unsupported Node
version stops before npx. Nothing installs these prerequisites automatically.

The package pin fixes the BMad CLI/core version. Explicit module tags select
TEA v1.27.2, BMB v2.2.2 and CIS v0.3.2. Fresh completion requires those versions
and pinned channels in the observed manifest. Tags can move and npm transitive
dependencies can resolve newer versions; these pins are not a cryptographic lock. Installation metadata records
observed versions, module provenance, tool IDs and the manifest hash; unknown
values remain unknown. The bounded reader supports the pinned manifest writer's
YAML subset and legacy module names, not arbitrary YAML. Unsupported syntax is
reported as unknown instead of partially interpreted. Output verification accepts
at most 1,024 inventoried skills, 4 MiB per skill, and 64 MiB in aggregate across
the inventory and selected host copies. These limits leave room above the pinned
installation while bounding observation of untrusted upstream output. Exceeding
a limit leaves completion unverified and reports the attempt as failed.

The earlier command without module pins failed when TEA resolved to v3.0.2,
which lacks the module definition expected by BMad 6.12.0. The approved pins
address that compatibility failure; existing or partial installations are still
preserved without an update or implicit retry. Observed commit SHAs are evidence,
not enforced source locks or proof that upstream code was safe to execute.

The official CLI may check for a newer release; the factory does not act on that
suggestion or switch package versions. npm can use its cache, and upstream defaults
can contain local identity. Raw installer output is suppressed; keep generated
consumer files private unless reviewed for publication.

## Preservation and transaction boundaries

Any recognized BMad tree, manifest or host artifact causes reuse without invoking
upstream, including old, malformed and partial installations. Adding a factory
host does not silently update BMad's tool selection. Inspect the observed `ides`
and decide any BMad migration separately. Factory uninstall never owns BMad files.

The earlier staging proposal in ADR 0007 differs from the concrete actual-project
invocation contract. This implementation follows that invocation contract: factory
projection publication is one transaction; direct upstream provisioning and its
provenance record are a separate phase. It does not provide a single atomic
transaction or sandbox npm code. A nonzero exit, timeout, missing outputs or
changes to factory files is reported as failed. Partial upstream effects remain for
inspection; the factory does not delete them or automatically retry a failed
attempt. A zero upstream exit without verified manifest and per-module host skill presence
is not proof. The wrapper can exit zero because factory publication succeeded
while reporting `BMad failed`; check the BMad status separately. Output conflicts
can leave factory files needing manual reconciliation and return a nonzero exit.

Inspect `_bmad/_config/manifest.yaml`, BMad host skills and the `bmad` section of
`.software-factory/installation.json` before manual recovery. Preserve needed
work and resolve partial files before explicitly arranging another attempt.
The factory does not reinterpret third-party provenance as file deletion rights.

## Official sources

- [Pinned command](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/commands/install.js)
- [Package and Node requirement](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/package.json)
- [Skill inventory and cleanup contract](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/core/manifest-generator.js)
- [Manifest writer](https://github.com/bmad-code-org/BMAD-METHOD/blob/v6.12.0/tools/installer/core/manifest.js)
- [npx option ordering](https://docs.npmjs.com/cli/v10/commands/npx/)
