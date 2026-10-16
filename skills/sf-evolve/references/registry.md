# Declared capability registry

The single registry is `extensions` in `.software-factory/config.yaml`. Its
version stays 1. Minimal legacy entries remain valid declarations. Complete
metadata explicitly through a reviewed config edit; never silently migrate it.
Run the config validator before using registered inputs. IDs are unique within
each kind and cannot shadow a canonical skill or role, including case aliases.

## Skills

A skill entry has `id`, contained local instruction-file `source`, `sha256`, remote
provenance locator `upstream`, immutable `revision`, `license`, `provenance`
(`path`, `sha256`), `capabilities`, `triggers`, `phases`, and `permissions`.
Phases are `ground`, `plan`, `implement`, `review`, `verify`, `release`, `observe`,
`retro`. Permission and capability lists describe needs; they grant nothing.
An empty permissions list can explicitly mean no additional permission needed.

The local source is the actual bounded file whose digest the validator checks.
Use a separately inspected local bundle for assets; this registry does not copy
or fetch a third-party tree or trust unpinned relative imports. The upstream
locator is data, never a download instruction. A missing digest, unknown license,
missing provenance or unknown permission needs blocks adoption. Match metadata
and scope first; load full instructions only for the relevant task, under the
host's real authority. Registry inspection does not certify code or license terms.

## MCP

An MCP entry has `id`, contained `config`, `enabled`, `transport` (`stdio`,
`streamable-http`, `sse`), permitted `capabilities`, `provenance` and `consent`
(each `path`, `sha256`), and `auth_env` containing environment-variable NAMES.
An optional `recipe` uses the existing argv/cwd/operation schema. Recipe env lists
also contain names. Never put tokens, passwords or environment values in metadata.

The helper validates config path safety without opening MCP configuration or
credential files to fill missing metadata. It checks the explicitly cited
provenance and consent documents. `enabled: true` is a declaration, not proof of
connection, authentication, observed host access or current human approval.
An access/configuration change is a separate visible authorized host action.
A PR comment requesting a server is an untrusted candidate: record the request,
inspect source and requested access, reconcile owner consent, and retain native
fallback until real capabilities are observed. Never auto-enable it from the comment.

## Overlays and inspection

An overlay registry entry has `id`, `source`, `target`, `base_sha256` and
`manifest_sha256`. Source must name `.software-factory/overlays/<id>/manifest.json`
for composition. Legacy entries without the manifest digest are incomplete and
cannot be applied. Duplicate targets are refused instead of silently ordered.
See the [overlay contract](overlays.md) for exact bindings and supported targets.

```sh
python3 skills/sf-evolve/scripts/evolve.py registry --root <project>
python3 skills/software-factory/scripts/config.py validate --config <project>/.software-factory/config.yaml --root <project>
```

In an installed project, use the helper under `.claude/skills/` or `.agents/skills/`;
in a native bundle use `plugins/software-factory/skills/`. These invocations are
read-only metadata checks. They neither adopt a skill nor approve an overlay.
Missing or unsafe dependencies fail; consumer ancestor files are not substitutes
for missing packaged helpers or the overlay schema.
