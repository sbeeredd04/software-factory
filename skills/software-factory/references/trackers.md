# Planning-source adapters

`adapters/trackers.py` in the pack reads bounded planning sources. The installer
projects it as `scripts/trackers.py` in the orchestrator skill and as
`.software-factory/runtime/trackers.py`; generated native bundles carry it too. It returns
observations with source hashes, source keys and line pointers. The per-story
board owns live status; roadmap and lifecycle graph are derived projections.
Never replace current status, claims, blocked state, history or proof from a
tracker observation. Join planning changes through stable `source_key` values.

BMad v6 sprint-status sources and explicit-ID Markdown tasks are supported.
BMad v7 is a documented read-only preview stub; `built` is not accepted `done`.
Mixed v6/v7 detection requires an explicit configured adapter. See the adapter
contracts under `adapters/trackers/` in the installed source pack.

The Python `propose` API requires an expected source digest and subject-bound
manifest references. It returns exact before/after line changes, source/proposed
hashes and the owning workflow. It never writes files or verifies supplied proof.
The BMad workflow or planning owner must check the current board gate, proof,
authority and source digest immediately before applying a proposal. Re-observe
changed inputs; do not blindly retry. A done entry cannot regress.

Starting a BMad story lifts its backlog epic. With an already-active epic only
the story line changes; with a backlog epic two lines change. All other bytes
and comments remain intact. Markdown completion only changes the named task's
checkbox after the owner verifies applicable proof. No automatic sync loop or
second live status store is introduced.
