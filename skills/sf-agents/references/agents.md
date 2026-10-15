# Registry and observations

The approved config's `agents` map owns registry declarations. `kind: native`
means host invocation (including direct work by the current worker); `external`
means a declared argv recipe. Cursor and Codex can be either mode. Do not add
vendor-specific kinds or treat native as an executable named `claude`.

`agents.py discover` returns deterministic JSON: per-entry presence and source,
unknown version/auth/effective model, config hash and observed file hashes.
Detection uses `shutil.which`, host-provided native inventory, or a contained
known file. It does not run `--version`, auth, model-list or network probes.
No `claude`, `cursor-agent`, `codex`, or `agent` alias is ever executed by the
helpers/tests. Historical version/auth-probe criteria are superseded by this
repository's no-agent-execution rule and config25's presence-only contract.

Registry examples (merge only through reviewed configuration):

```json
{
  "native": {"kind":"native", "description":"Current host worker",
    "risk_tiers":[0,1,2,3], "detection":{"kind":"native-inventory"}},
  "cursor": {"kind":"external", "description":"Declared Cursor analysis",
    "risk_tiers":[0,1],
    "detection":{"kind":"executable-presence","executable":"cursor-agent"},
    "invoke":{"argv":["cursor-agent","-p","--mode","ask","--workspace",
      "{workspace}","{task_file}"],"cwd":".","operation":"observe"}},
  "codex": {"kind":"external", "description":"Declared Codex analysis",
    "risk_tiers":[0,1,2],
    "detection":{"kind":"executable-presence","executable":"codex"},
    "invoke":{"argv":["codex","exec","--sandbox","read-only","--cd",
      "{workspace}","{task_file}"],"cwd":".","operation":"observe"}}
}
```

These are unexecuted recipe shapes, not compatibility or availability proof.
`task_file` is a literal argument naming a brief, not implicit stdin/file expansion;
write the approved recipe to instruct the selected host how to read that brief.
For an already approved Codex coding recipe, `workspace-write` requests the
workspace policy; actual host permissions still govern. Native Codex custom
agents inherit parent permissions and model; reviewer prose alone is not an
enforced read-only sandbox.

Current Cursor documentation uses the executable name `agent`; a consumer's
configured executable must match their actual setup. Its `--force` is force-allow
and an alias of `--yolo`, not a safe automatic edit switch. Config validation can
accept an explicitly declared legacy `cursor-agent --force` recipe pinned to a
workspace; this renderer refuses to present it as dispatch-ready. It never adds
trust, forced approval, MCP approval or sandbox-bypass flags.

`render-invocation --agent ID --values FILE` substitutes only the five documented
whole tokens: workspace, task_file, output_file, model and branch. Values are
literal argv, not shell interpolation. The workspace/cwd must identify the exact
claimed worktree; a missing requested model remains missing, never guessed.
Environment values remain `env:NAME` references and are not read or printed.

Pass `discover --inventory FILE` for host observations `{ "native": true }`.
An absent inventory leaves presence unknown. A native fallback can mean the
current worker doing the work directly; it does not assert spawned subagents
exist or that any worker is currently running. Binary presence is not usability.

Official sources: [Cursor parameters](https://cursor.com/docs/cli/reference/parameters),
[Codex CLI](https://learn.chatgpt.com/docs/cli/reference),
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Static source checks do not establish account access, effective model or live
loading. The host resolves requests at dispatch and records observed facts.
