# Tracker adapter contracts

The board's per-story record is the only live status authority. These adapters
produce planning-source observations, not a separate state service.

- [BMad v6](bmad-v6.md): supported bounded parser and exact patch proposals.
- [Markdown](markdown.md): supported explicit stable IDs and patch proposals.
- [BMad v7](bmad-v7.md): read-only preview contract, parser not implemented.

`detect(directory, selected=None)` checks only `sprint-status.yaml` and
`tickets.toml` in the supplied directory. Mixed discovery requires configured
selection. Discovery does not execute host CLIs, inspect credentials, or authorize
writes. Missing discovery is unknown, not proof of a greenfield project.

```sh
python3 adapters/trackers.py --adapter bmad-v6 --path tests/fixtures/trackers/sprint-status.yaml
python3 adapters/trackers.py --adapter markdown --path tests/fixtures/trackers/tasks.md
```

The API accepts captured text, so callers can bind derivation to their own snapshot.
The CLI uses bounded, descriptor-relative regular-file reads and writes JSON only
to stdout. Limits are one MiB and 10,000 lines. No parser evaluates project code.
