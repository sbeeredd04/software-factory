# Configuration

Phase: configuration — reading the project's factory configuration before
grounding, planning, dispatch or proof.

## The contract

`.software-factory/config.yaml` in the consumer project is team-owned and
tracked. Version 1 stores the documented JSON-compatible YAML subset, so
standard-library tooling can parse it; anything outside the subset is refused,
never partially interpreted. `sf-help` drafts the file from its interview and
the human approves it; validate any change with the config helper, run from this
skill's directory:

```sh
python3 scripts/config.py validate --config "<project-root>/.software-factory/config.yaml"
```

The helper fails closed: an unparseable or semantically invalid config exits
nonzero with a clear explanation. It never executes anything the config
contains.

## What the keys mean for the loop

- **project / documents** — the repositories in play and the paths of the
  principle, architecture and convention documents. Grounding reads these; the
  principles documents are the only principles authority, referenced, never
  copied.
- **tracker** — the planning source: `bmad-v6` (sprint status), `markdown`, or
  the `bmad-v7` read-only preview adapter. The tracker feeds planning; story
  status lives in the per-story board record.
- **planning** — `method: bmad` for new setup; native requires explicit selection,
  scoped fallback or preservation of an approved legacy route. `depth` sizes the
  planning work. A tracker adapter never proves that BMad ran.
- **branches** — the integration branch (default `dev`) and the protected
  branches (default `main`). Integration merges go to the former; the latter are
  never pushed or merged to directly. The two are never the same branch.
- **environments** — named deploy/proof targets whose commands are documented
  argv recipes classified `observe` or `write`. They are configuration for
  authorized tasks, executed only under approved authority — never by hooks and
  never by the helpers.
- **agents / routing** — the registered agents (kind, presence-only detection, allowed
  risk tiers) and the risk-tier routing table. The native host worker is the
  mandatory fallback: if a configured external agent is absent or unsuitable,
  the route degrades to native, never to weaker proof. Detection probes are
  local presence checks only.
- **review_bots** — optional review bots. Nothing is required by default; a
  required bot's report must bind to the current HEAD before it counts. Optional
  `authors` lists exact GitHub logins for attribution; absent/empty means unknown,
  never match-anything. `reader` names a host observation capability, never shell
  text for helpers to execute. `triage` intentions do not grant write authority.
- **verification** — the required check names as a unique list the gate enforces (see
  [evidence](evidence.md)).
- **autonomy** — defaults: local work within the request; external actions
  (push, PR, merge, deploy) ask first unless a standing delegation covers the
  exact scope. `mode: risk-adaptive` enables the protected delegated acceptance
  route only with current finite owner authority and independent consequence
  evidence; `supervised` or absence retains human epic acceptance. See [authority](authority.md).
- **checkpoints / budgets** — when checkpoints are taken; `manual: true` reserves
  human acceptance, while new setup proposes false with durable checkpoints and
  consequence-driven escalation. Epic `hitl` and story reservations remain binding.
  Existing profiles are never silently rewritten. Budgets are alarms by
  default, not silent task abandonment. `budgets.max_parallel_workers` is an
  optional owner ceiling: omit it when the owner sets no ceiling. Actual observed
  host capacity always bounds dispatch; unknown capacity calls for conservative
  dispatch and never counts as a capability declaration.

Semantic rules the validator enforces: the routing fallback exists, referenced
documents exist, and the protected and integration branches differ. A missing
config means the pack has not been set up yet — route the human to `sf-help`
instead of inventing defaults silently.

## Detailed contracts

- [Schema and semantic rules](config-schema.md) — supported subset, limits, recipes and paths.
- [Planning-source adapters](trackers.md) — observations and owner-mediated patch proposals.

The structural configuration fixture is `examples/config/config.yaml` in the
source pack. It includes disabled monitoring, empty integrations and a native
fallback. Its nested Shopfront eval, Playwright references, copied signoff and
synthetic digest demonstrate accepted shapes; they establish no consumer run
readiness or owner approval. Setup authors a consumer eval draft and records
confirmed, defaulted and unknown answers with config digest references in a
separate setup receipt. Policy fields are input declarations; configuration
validation does not authenticate owner decisions, start monitors, or execute
discovery probes.

`extensions` is the declared skill/MCP/overlay registry. Source pins, provenance,
permissions and consent are metadata to reconcile, never installation or access
proof. `checkpoints.retro_cadence` governs the existing learning checkpoint.
Use [sf-evolve](../../sf-evolve/SKILL.md) for metadata completion and reviewed
persistent customization; its installer integration refuses unsafe/drifted inputs.
