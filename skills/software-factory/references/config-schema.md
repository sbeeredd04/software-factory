# Configuration schema and validation

The canonical contract is `schemas/config.schema.json` in the pack. The installer
projects it next to the runtime validator and into the generated orchestrator
skill's `schemas/` directory. Generated native bundles include that projection.
Raw portable skill discovery alone does not perform full project setup; use the
installer before invoking schema-dependent configuration validation.

## Syntax and evaluator

Config is strict JSON in a `.yaml` file: no YAML aliases, multiline scalars,
comments, duplicate keys, non-finite numbers, or implicit conversion. Canonical
`version` is integer 1; other versions fail. `parse` and `load` check syntax only;
`validate_data(data, root, schema=None, check_paths=True)` performs full checks
without reopening the config. `check_paths=False` checks declarations only and
must never be reported as filesystem or setup readiness. Captured Path-like roots
may supply required document bytes; they must preserve their own provenance.

Supported JSON Schema 2020-12 subset: `type`, `required`, `properties`,
`additionalProperties`, `patternProperties`, `items`, `enum`, `const`, `oneOf`,
`minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, local `$ref`,
`minItems`, `maxItems`, `uniqueItems`. Supported annotations are `$schema`, `$id`,
`title`, `description`, and `$defs`. Unknown keywords are rejected even in unused
branches. References must name a local `$defs` entry; remote and recursive
references fail. Schema regexes are trusted shipped contract data, not a facility
for running arbitrary user regex validators. This is not a general schema engine.

Limits: one MiB per config/document read, 32 nested levels, 20,000 entries,
128-character keys and 16,384-character data strings; schema fields usually
limit strings to 2,048 characters and arrays to 1,000 entries. Failures name a
bounded key path or JSON line/column without echoing values.

Optional differential check, when the package is already available:

```sh
SF_CONFIG_JSONSCHEMA_CROSSCHECK=1 python3 -m unittest discover -s tests -p test_config_schema.py -v
```

Absent `jsonschema` explicitly skips that check. Default shipped validation and
tests use only the standard library. The differential check compares schema
results; document and authority-reference semantics remain the pack's checks.

## Semantic checks

- `project.root` resolves from the config directory (normally `..` for the
  conventional config path). Every other path is relative to that root. An
  explicit `--root` must agree. Cwd never controls reference resolution.
- Four named principles documents, architecture, conventions, extra context and
  the tracker source must be readable, nonempty regular files within the root.
  Symlink and special-file reads fail; descriptor-relative reads resist path
  replacement redirection. Output paths may be absent but cannot escape the root.
- Routing must resolve and have a native fallback supporting tiers 0–3. Agent
  declarations request models; they do not establish runtime availability,
  credentials, actual model identity or reviewer independence.
- Integration cannot be a protected branch; required bots cannot be disabled.
- Agent/environment/MCP command declarations are nonempty argv recipes, never
  shell-command strings. Whole-token placeholders: `{workspace}`, `{task_file}`,
  `{output_file}`, `{model}`, `{branch}`. Embedded/unknown placeholders and shell
  substitution fail. `--force` and equals forms require a declared `cursor-agent` executable and
  `--workspace {workspace}`.
- Known credential shapes, raw credential fields and bounded high-entropy token
  heuristics fail anywhere. Digests and environment-reference names are allowed.
  This heuristic can flag unusual prose and is not comprehensive secret scanning.
  Permission-bypass flags fail in separated or equals forms. Values are redacted.
- Extensions remain contained and cannot target board/run/config authority stores.
  Registration never installs a skill, enables MCP or applies an overlay.
- Monitoring defaults disabled. Enabled monitoring requires scoped sources,
  environment references, data-policy documents, an authority reference and an end
  condition. These are declarations for the host; no scheduler or monitor starts.

The nested `eval` object preserves the eval runner's command strings:
`harness.run`, command/golden grading declarations. They are an explicit exception
to argv recipes, executed only by the eval owner under task authority. Export the
nested object unchanged to `eval.plan_file`; the validator never writes it.
Harness `file_state` and grade `state` are different enums. Eval schema validity
is not signoff, case readiness or proof that all declared policy is runner-enforced.

`verification.required_checks` remains a unique list of check names. Evidence,
review, SHA bindings and checkpoint applicability belong to the gate and board
owners; config validation does not duplicate their schemas or evaluate receipts.

## Setup mappings for optional sections

These are declarations to populate during setup, not discovered capabilities.
The exact shapes are in the canonical schema at the following JSON pointers:

- `/$defs/environment`: each `environments.<id>` requires `kind` (`local`,
  `preview`, `staging`, `production`), `expected_host` and `shared_resources`.
  Optional `deploy` and `proof` use `/$defs/recipe`: `argv`, `cwd`, `operation`
  (`observe` or `write`), with optional environment references and bounded limits.
- `/$defs/decision`: `autonomy.standing_delegations[]` and environment
  `write_authority` use `source`, `sha256` and `scope`. Setup must link the real
  owner's applicable decision; a valid digest shape does not authenticate it.
- `/properties/review_bots`: each bot requires `enabled`, `required`, `config`;
  optional `reader` identifies the review source and `triage` is `propose` or
  `authorized-apply`. Store these inside `review_bots.<id>`. A triage declaration
  does not itself authorize applying a suggestion.
- `/properties/operations`: `sources[]` requires `id`, `environment`, `kind`,
  `locator`, `read_scope`, `data_policy_ref`, `trigger_refs`, `dedup_keys`.
  Enabled observation also requires `authority_ref` and `until`. The source-linked
  authority and trigger documents must record notification destination, each
  source's observation window and cadence, triggering conditions and repair scope.
  `schedule_request` requests host scheduling; it creates no scheduler. Unknown
  monitoring capability stays unknown until host access is observed and granted.
  `followup: authorized-repair` does not grant deploy or rollback authority.

The setup receipt records which answers were confirmed, defaulted or unknown,
alongside the config digest and source decision references. It is setup evidence,
not a second live status store. `tracker.options` is unsupported: use the selected
adapter's documented shape and owner workflow. The schema and validator check
structure and references; the host still checks actual access and authority.

## Extension metadata and composition

Skill metadata adds `upstream`, `revision`, `license`, `provenance` (`path`,
`sha256`), `capabilities`, `triggers`, `phases` and `permissions` to `id`, `source`
and optional `sha256`. MCP adds `transport`, `capabilities`, `provenance`,
`consent` (both bound path/digest pairs) and `auth_env` names to its legacy fields.
Overlay entries add `manifest_sha256`; this pin is mandatory for composition.
Legacy minimal entries remain incomplete declarations. IDs are unique per kind;
canonical skill/role collisions and duplicate overlay targets fail. All declared
source/provenance/consent pins are checked when filesystem checks are enabled.
MCP config contents are never opened by the validator to discover credentials.

Overlay targets cannot alias configured governing documents, context or decision
stores, MCP/bot configuration, or operations data-policy documents. Comparisons
conservatively reject case aliases on every platform. The sf-evolve composer further restricts targets to generated Markdown
skill entries/references with preserved frontmatter. See the
[registry](../../sf-evolve/references/registry.md) and
[overlay](../../sf-evolve/references/overlays.md) contracts for exact supported
fields and provenance limits. Schema validity alone never grants approval.
