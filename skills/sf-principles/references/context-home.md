# The project-context home

`.software-factory/context/` is the committed project-context home: the durable
context read before planning, designing and reviewing. Only the volatile siblings
(`runtime/`, `backups/`, `runs/`, `active.json`, `state.lock`, `board.lock`,
`installation.json`) are ignored — never `context/`.

## Layout and owners

| Path | Content | Owner |
| --- | --- | --- |
| `principles/{product,conventions,risk,evals}.md` | core principles, user-authored | `sf-principles`, with `sf-help` setup |
| `CODEBASE.md` | codebase map | `sf-crawl` |
| `board/streams.json`, `board/epics/*.json`, `board/stories/*.json` | per-story records, the progress truth | the board helper (`roadmap.py`) |
| `board/plan.json` | planning source the records derive from | the planning step (`roadmap.py derive`) |
| `board/roadmap.json`, `board/dashboard.html` | regenerable projections | `roadmap.py build` |
| `decisions/NNNN-title-with-dashes.md` | decision records | the design module |

Exactly one owner per file; each owning skill creates its own paths. The installer
creates nothing inside the context home, overwrites no artifact and generates no
body, so its ownership manifest lists no context path.

## Decision records

Write a record only past the significance bar: a cross-module or layer-contract
change; adopting or changing an architecture pattern; adding or changing a
third-party boundary (persistence, queue, auth, model provider); a
deployment-topology change; reversal cost above a day. Never for class-internal
choices, dependency minor bumps or refactor picks. A pre-existing decision
directory is pointed at, never duplicated.

One decision per file `decisions/NNNN-title-with-dashes.md`, at most 40 lines —
a record that needs more is two records. Ordered sections: title; context and
problem as facts in a few sentences; decision drivers; at least two genuinely
considered options; the chosen outcome with a one-sentence reason; consequences,
bad ones included; confirmation naming the fitness function, test or review that
proves compliance, or stating none exists. Numbering is monotonic, never reused;
lifecycle `proposed → accepted → superseded-by-NNNN`; superseded records are kept,
never deleted. Re-read the area's record before re-deciding and, if the context
changed, write the superseding record in the same change; a record conflicting
with the principles stops and surfaces to the human, never silently resolved.
