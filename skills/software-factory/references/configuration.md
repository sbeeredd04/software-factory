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
python3 scripts/config.py --config "<project-root>/.software-factory/config.yaml"
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
  the `bmad-v7` read-only preview adapter. The tracker feeds planning; the
  per-story board record is the only live story-status store — never chat,
  never the tracker itself.
- **branches** — the integration branch (default `dev`) and the protected
  branches (default `main`). Integration merges go to the former; the latter are
  never pushed or merged to directly. The two are never the same branch.
- **environments** — named deploy/proof targets whose commands are documented
  argv recipes classified `observe` or `write`. They are configuration for
  authorized tasks, executed only under approved authority — never by hooks and
  never by the helpers.
- **agents / routing** — the registered agents (kind, detection probe, allowed
  risk tiers) and the risk-tier routing table. The native host worker is the
  mandatory fallback: if a configured external agent is absent or unsuitable,
  the route degrades to native, never to weaker proof. Detection probes are
  local presence checks only.
- **review_bots** — optional review bots. Nothing is required by default; a
  required bot's report must bind to the current HEAD before it counts.
- **verification** — the required check names per phase the gate enforces (see
  [evidence](evidence.md)).
- **autonomy** — defaults: local work within the request; external actions
  (push, PR, merge, deploy) ask first unless a standing delegation covers the
  exact scope. See [authority](authority.md).
- **checkpoints / budgets** — when checkpoints are taken; budgets are alarms by
  default, not silent task abandonment.

Semantic rules the validator enforces: the routing fallback exists, referenced
documents exist, and the protected and integration branches differ. A missing
config means the pack has not been set up yet — route the human to `sf-help`
instead of inventing defaults silently.
