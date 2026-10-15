# Resume from durable facts

Read status before action. An active run keeps its owner, claims, checkpoint and next action through a host-session reset; claims do not expire automatically. The status command is read-only and does not dispatch or refresh derived views. Reestablish the [quickstart variables and installed helper paths](quickstart.md#preview-and-install) in a new shell before these commands.

```sh
"$SF_PYTHON" -I -B "$SF_KERNEL/state.py" status --workspace "$SF_PROJECT"
"$SF_PYTHON" -I -B "$SF_KERNEL/state.py" reconcile --workspace "$SF_PROJECT"
"$SF_PYTHON" -I -B "$SF_KERNEL/state.py" audit --workspace "$SF_PROJECT"
git -C "$SF_PROJECT" rev-parse HEAD
git -C "$SF_PROJECT" status --short
```

The orchestrator compares the saved claim owner and path scope with actual Git worktrees, HEADs, dirty files, review receipts and external outcomes. Reconcile before assigning another worker or retrying an uncertain push/deploy/message. `reconcile` can report gaps; it cannot prove a process lives or an effect succeeded. Preserve failed and unknown evidence. The [canonical recovery contract](../skills/software-factory/references/recovery.md) specifies checkpoint fields, repair and release.

Only the run owner initializes or repairs a run. A broken pointer does not authorize a reset; inspect the retained program first. Before handoff, save the exact five-key checkpoint notes (`objective`, `next`, `completed`, `decisions`, `open_questions`) from current facts. Board projections and lifecycle graph are derived from owned records; their read-only queries cannot create delivery proof. [Verification](verification.md) explains current subject and effect evidence.
