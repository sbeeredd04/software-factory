# Decision records

Where: `decisions/NNNN-title-with-dashes.md` under the project-context home —
or a pre-existing decision directory the project already uses, discovered and
pointed at, never duplicated. This file is the authoring contract; the home
layout and its per-file owners are stated in the principles skill's
context-home reference. The pack's own decision records follow the same shape
and bar, so the taught contract is the dogfooded one.

## Significance bar

Write a record only for: a cross-module or layer-contract change; adopting or
changing an architecture pattern from [architecture-patterns.md](architecture-patterns.md);
adding or changing a third-party boundary (persistence, queue, auth, model
provider); a deployment-topology change; or anything whose reversal costs more
than a day. Never for class-internal choices, dependency minor bumps, or
refactor-technique picks — those live in the diff.

## Record contract

- One decision per record, at most 40 lines; a record that needs more is two
  records.
- Ordered sections: title; context and problem stated as facts in a few
  sentences; decision drivers; at least two genuinely considered options — a
  record with one option is a note, not a decision; the chosen outcome with a
  one-sentence reason; consequences with the bad ones included; and a
  confirmation naming the fitness function, test or review that will prove
  compliance, or stating that none exists.
- Numbering is monotonic and never reused. Lifecycle: `proposed → accepted →
  superseded-by-NNNN`. Superseded records are kept, never deleted.

## Re-read and escalation

Before re-deciding an area, read its record first; if the context changed,
write the superseding record in the same change. A record that conflicts with
the project principles stops and surfaces to the human owner named in the
project's risk module with a recommendation — it is never silently resolved;
the resolution is written as a superseding decision record, and a change to
the law itself is a proposed principles edit.
