# Derived lifecycle graph

`trace.py` connects existing board facts, code surfaces and evidence without
creating a second status store. The orchestrator still decides scope and staffing;
the graph neither dispatches agents nor calls Git, models or the network.

## Commands

Run from this skill's directory, using the consumer workspace:

```sh
python3 scripts/trace.py query ready --workspace "<project-root>"
python3 scripts/trace.py query blocked --workspace "<project-root>"
python3 scripts/trace.py query unproved --workspace "<project-root>"
python3 scripts/trace.py query stale --workspace "<project-root>"
python3 scripts/trace.py query shipped --workspace "<project-root>"
python3 scripts/trace.py query decisions --workspace "<project-root>"
python3 scripts/trace.py query path --workspace "<project-root>" \
  --from story:1 --to requirement:AC-1
python3 scripts/trace.py build --workspace "<project-root>"
```

Queries derive fresh JSON from source records, never from saved `roadmap.json` or
`lifecycle-graph.json`. They do not update records or regenerate projections.
Queries open the existing board lock read-only and acquire the same bounded lock.
If that lock is absent, a query refuses without creating files or directories;
run an explicit build to establish synchronization. Only explicit `build` writes the derived
`lifecycle-graph.json` in the configured board directory. `--output` may name a
different contained file with that basename, separate from every consumed source.
Deleting this projection loses no authority or evidence.

Every invocation reads validated version-1 board records under the board lock.
The existing board validators and readiness calculation consume an in-memory
snapshot of captured board, config and validated claim bytes; they never reread
live files for answers. Captures are checked again after derivation and before
publication; changed bytes, file identity or directory contents require a retry.
Claim files have their own writers and receive the same consistency check. A missing active pointer is normal;
a broken existing ownership source refuses derivation. Failed builds leave the
previous projection intact. A saved projection is a snapshot; use a fresh query
for current source facts.

## What each question means

- `ready`: the board's dependency-ready, unclaimed frontier. It does not grant GO
  or imply a worker is running.
- `blocked`: prerequisite waits, explicit blockers and board problems. Additional
  board consistency diagnostics appear in the full graph.
- `unproved`: requirements without an explicit current passing receipt that cites
  them and has a matching local artifact digest. `covers` alone never qualifies.
  This is structural support, not independent acceptance or proof that an effect
  occurred; an arbitrary receipt cannot authenticate its author.
- `stale`: a receipt whose subject differs from a known current subject, or whose
  artifact is missing or differs from its recorded digest. An unknown current
  subject remains `unknown`, rather than being invented from record order.
- `shipped`: separate recorded `done` stories, recorded merge identities and
  deployment reports. Local status does not establish actual shipping; the
  answer explicitly leaves shipping verification unestablished.
- `decisions`: the board's human decision queue. Records preserve provenance;
  the orchestrator reconciles actual authority with the trusted user source.
- `path`: a directed path of typed links, including provenance. Traversing a
  declaration does not turn it into verified coverage or execution authority.

## Nodes, edges and explicit extensions

The versioned JSON format is `sf-trace/1`. Nodes appear only for recorded facts:
requirements, epics, stories, surfaces, claims, receipts, findings, commit/PR
identities, deployment/effect reports, decisions and checkpoints. A claim records
assignment with unknown process liveness. A checkpoint grants no new authority.
A bare full commit SHA is a recorded identity, not a verified Git object.
Decision files under the committed context home are indexed without interpreting
prose as human approval.

Stable IDs include `story:1`, `epic:1`, `requirement:AC-1`,
`surface:src/example.py`, `receipt:1:tests`, `commit:<full-sha>` and
`decision:<workspace-relative-path>`. Records may already use extension fields;
the helper reads these without modifying the board schema or its source files:

- `links`: an array of objects with `relation` and a typed graph-ID `target`.
  Recognized relations are `depends-on`, `covers`, `implements`, `verifies`,
  `reviews`, `supersedes` and `deployed-as`. Unknown relations refuse derivation;
  missing targets receive a diagnostic. The links remain declarations.
- A receipt's `verifies` array explicitly names graph IDs. Structural support
  additionally requires reported `status`, `verdict` or `result` equal to `pass`,
  `artifact` naming a contained workspace-relative file, matching
  `artifact_sha256`, and its `subject_sha` matching the story's known subject.
- Current subject means `merged_sha` on a done story, otherwise the optional
  explicit `review_subject_sha`. No fallback promotes a baseline or a historical
  completion attestation into proof of the current result.
- Receipt `decision_ref`/`decision` names a contained decision source; absence is
  reported. Receipt `deployed_sha`, `environment` and `effect` produce recorded
  reports, never live environment observations.

Structural links (`part-of`, `scope`, `records`, `subject`, `assigned-to`) reflect
literal fields. Declared scope is not implementation proof. Prerequisite and
supersession cycles are rejected. Factual code import/call cycles are retained.
Frozen historical records are read as they stand; missing verification fields
remain unknown and are never retrofitted.

## Optional code-map input

Pass `--crawl <workspace-relative-json>` to consume an existing `sf-crawl/1`
report created by [sf-crawl](../../sf-crawl/SKILL.md) with `--json`. This helper
does not crawl or execute project code. It reads Python module paths, internal
imports and explicitly resolved call records; unresolved targets are diagnosed.
Other language relationships are not inferred.

Crawl v1 reports contain no per-file content hashes. The graph fingerprints the
current report and source bytes, but that does not prove the report was generated
from those source bytes. Imported relationships therefore state that their
current source binding is unknown. Refresh with sf-crawl when needed; do not
claim current runtime wiring or cross-language coverage from this graph.

## Provenance, bounds and failures

Every node and edge cites a workspace-relative source path, JSON pointer or line,
and the SHA-256 of the captured source bytes. `inputs` lists file and directory
observations; `source_fingerprint` hashes that list. Dirty bytes count, regardless
of HEAD. No absolute worktree/repository paths from claims are copied into output.
Directory scopes are not recursively scanned and carry an explicit limitation.

Bounds are 1,024 source files/entries per directory, 1 MiB per source file,
16 MiB total input, 10,000 nodes, 20,000 edges/diagnostics and 16 MiB output.
Paths must name entries inside the workspace; a root-only `.` path is refused.
Selected sources and outputs use descriptor-relative no-follow directory walks;
regular-file reads are nonblocking and reject symlinks, path escapes and special
files. Publication anchors its temporary file and replacement to one validated
parent descriptor. Queries also avoid writing bytecode caches in the skill pack.
Malformed records, unsupported versions, cycles, exhausted bounds and concurrent
source replacement exit nonzero before replacing a saved projection. Missing
referenced surfaces/decisions, dangling links and unverified code bindings remain
visible diagnostics. Helpers validate local facts and structure; independent
review and real permissions still establish acceptance and authority.
