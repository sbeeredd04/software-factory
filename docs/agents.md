# Agent registry and routing

`sf-agents` supplies presence observations and route/invocation proposals for the
host orchestrator. It never executes agent CLIs, probes authentication/models,
or relaxes permissions. Native fallback means the host worker within actual
scope; it does not prove a spawned agent is available.

See the canonical [registry](../skills/sf-agents/references/agents.md) and
[routing](../skills/sf-agents/references/routing.md) contracts. Requested models
and observed effective models are separate. Preserve11skills and11roles; use the
expertise needed rather than a fixed fleet. Missing optional agents/gh do not
block local work. Permission denials do not authorize another backend.

Full project install or generated native bundles supply the sibling setup/config
helpers, schema, templates and publication helper. Source skills discovery is
skills-only; missing assets require full setup, never downloading dependencies
or importing arbitrary consumer modules. Invoke helpers with Python3.11+ `-I -B`
for isolation from consumer Python modules and bytecode writes.
