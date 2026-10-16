# BMad v7 preview

Read-only documented stub, not implemented in v0.1. Detect an initiative directory
containing `tickets.toml`, with planning artifacts such as `<type>-<slug>-plan.md`.
Do not infer its full status grammar or migrate v6 files. The parser explicitly
refuses v7 input, and there is no v7 write API.

`built` describes implementation output. It is distinct from accepted `done`,
which requires applicable integration evidence and human acceptance. Mixed v6
`sprint-status.yaml` and v7 `tickets.toml` discovery requires explicit selection.
