# Host contract correction proposal

Status: source corrections implemented and independently reviewed; live host loading remains unverified. Sources checked 2026-10-15. [ADR 0022](../../.software-factory/context/decisions/0022-documented-host-contracts.md) records the current contract and evidence boundary. The recommendations below describe the design that was implemented; doctor observations remain part of the installer lifecycle work.

## Shared Cursor and Codex skills

Keep one canonical source tree under `skills/`, and one generated shared consumer payload under `.agents/skills/`. A generated payload is allowed to contain host projection fields; canonical frontmatter remains standard-only.

For the six entry/admin skills (`software-factory`, `sf-help`, `sf-agents`, `sf-evolve`, `sf-eval`, `sf-principles`):

- When Cursor is an installed host, inject `disable-model-invocation: true` into the generated SKILL.md frontmatter. Cursor documents that exact field as its explicit-only mechanism. A pointer rule saying a skill is explicit-only does not implement this behavior.
- When Codex is an installed host, generate `agents/openai.yaml` with `policy.allow_implicit_invocation: false`. Preserve sf-crawl's explicitly allowed working-skill policy and keep the other working skills implicit.
- Derive shared bytes from the union of already installed hosts and newly requested hosts, not only the current `--host` argument. Otherwise a subsequent Codex install removes Cursor's field, or a subsequent Cursor install drops ownership of Codex policy files. Host removal is a separate explicit migration/uninstall action.

Codex's current official Build skills documentation requires name/description and documents openai.yaml policy, but does not establish whether unknown SKILL.md frontmatter fields are ignored, rejected, or interpreted. The reviewed official pages and two targeted official-domain searches did not establish that guarantee. Therefore describe the combined shared payload as format-tested with live host loading unverified. Do not turn a local YAML parse into a claimed Codex compatibility proof.

Recommendation: implement both documented policy mechanisms in one generated payload and expose the cross-host extension tolerance as an explicit unverified capability. Do not silently weaken Cursor invocation policy. If the release requires a guarantee for every supported Codex version, hold that release claim until it has a permitted source-level parser fixture or independent host observation. No host CLI should be invoked to obtain it in this repository.

An alternative with separate `.cursor/skills` and `.agents/skills` trees does not automatically solve compatibility: Cursor documents that it discovers both roots, so it can load duplicate names. Avoid duplicate payloads, undocumented precedence assumptions, and host-specific canonical sources.

## Codex role permissions

Current standalone custom agents support name, description, developer_instructions and optional model/reasoning settings. They inherit parent permissions, provider and MCP configuration. In particular, sandbox_mode in a custom-agent file does not override parent permissions.

Proposed correction:

- Omit sandbox_mode from generated custom-agent TOML, rather than emit a field the pack describes as enforcing per-role isolation.
- Keep model omitted, preserving the existing inheritance decision.
- Preserve the canonical reviewer roles' independence and no-authoring instructions. If stronger wording is needed, add it to canonical role intent, not a falsely protective configuration setting.
- Do not disable shell tooling merely to simulate a read-only sandbox: independent verification may require running checks, and tool removal is a separate, explicit capability tradeoff.
- When enforced read-only access is required, the orchestrator must use an actually read-only parent/session or a verified supported restriction. If that capability cannot be observed, report the gap and block only that requirement's dependents.
- Do not change parent permissions, approval settings, trust flags, home configuration or service settings automatically.

Doctor observations should be separate: generated TOML structure can pass; per-role sandbox isolation receives a warning that parent permissions are inherited; live custom-agent loading is unverified; a configured requirement for enforced read-only review is blocked when no actual enforcing capability is established. Instructions alone never earn a sandbox-pass result.

## Narrow acceptance evidence

1. Canonical source frontmatter and bodies are unchanged by installation. Exactly the six generated Cursor entry/admin skills carry the boolean explicit-only field; all five working skills remain implicit.
2. Codex-only output has its existing openai.yaml matrix; combined output carries both hosts' invocation mechanisms without duplicate skill folders. Record combined Codex parser tolerance as unverified, not pass.
3. Every permutation of sequential host additions converges to the all-host projection, retains ownership/backups, and a subsequent all-host or individual-host reinstall is a byte-level no-op. Tests compare semantic manifest ownership too, excluding only volatile timestamps/identifiers.
4. Standalone TOML agents parse with name, description and canonical developer_instructions, omit model and sandbox_mode, and contain no permission-bypass fields. A negative fixture with sandbox_mode proves doctor does not report that field as enforcing isolation.
5. Doctor JSON/text distinguish format validation, observed host behavior, inheritance limitations and unmet enforced-readonly requirements. No unobserved host outcome becomes pass.
6. Existing malformed-config, settings preservation, hook merge, transaction rollback and guard-stub tests continue to apply. No real agent CLI, network model invocation or home write is needed.

## Official sources

- Cursor skill roots and explicit invocation: https://cursor.com/docs/skills (Skill directories; Disabling automatic invocation).
- Cursor agent readonly field: https://cursor.com/docs/subagents (Configuration fields).
- Codex local skill discovery and invocation policy: https://learn.chatgpt.com/docs/build-skills (Where Codex loads local skills; Optional metadata).
- Codex standalone custom agents and permission inheritance: https://learn.chatgpt.com/docs/agent-configuration/subagents (Approvals and sandbox controls; Custom agents).
- Codex hook shape and trust: https://learn.chatgpt.com/docs/hooks (Config shape; Review and trust hooks).

The earlier mission's sandbox_mode requirement and shared-payload field prohibition are superseded by ADR 0022. The correction removes an unsupported enforcement claim and emits the documented invocation controls. Stronger permission requirements still need an observed enforcing capability.
