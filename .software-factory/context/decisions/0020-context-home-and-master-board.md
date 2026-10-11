# 0020 — A committed context home and a master board of per-story records

Status: accepted · 2026-10-11

## Context

Workers degrade when context must be rediscovered each session; status
scattered across trackers, chats and run files invites contradiction.

## Drivers

- Durable context belongs in the repository, committed and reviewable.
- One live status store; everything else is a projection or a source.

## Options

- A parallel dashboard service or database: another system to run.
- Tracker-native tickets as the only truth: host-coupled and not
  projection-friendly.
- A committed `.software-factory/context/` home with per-story records and
  locked, regenerable `roadmap.json` and dashboard projections.

## Outcome

Principles, the crawl artifact, the board and the decision records live in
the committed context home; workers update only their own story records
and the generator owns the projections, because one store with
regenerable views cannot disagree with itself.

## Consequences

- `state.py` claims stay the path-exclusivity record; the board reads them.
- `done` and `cancelled` records are frozen history; corrections are new
  records, never rewrites.

## Confirmation

- `tests/test_board.py` covers ownership enforcement, regeneration
  determinism and diagnostics; this repository's own board is the worked
  example.
