# BMad v6

Supported subset: two-space `development_status` mappings; story keys
`<N>-<M>-<slug>`; story states backlog, ready-for-dev, in-progress, review, done;
epic states backlog/in-progress/done; retrospective optional/required/done.
Optional `planning_artifacts` is a two-space mapping of labels to links;
`action_items` is a two-space dash list of plain strings. Plain top-level metadata
is limited to generated/project/project_key/tracking_system/story_location.
Comments and blank lines are preserved. YAML aliases, tags, flow structures,
multiline scalars, duplicate keys and unsupported nesting fail closed. This is not
a general YAML parser. Extend an unsupported format through an explicit reviewed
adapter change; do not silently discard it.

Observations preserve source keys and statuses. Review can be translated to the
board's in-review vocabulary during planning import, but never overwrites the
board's current execution status.

`propose(text, 'bmad-v6', source_key, status, expected_sha256, evidence)` supports
in-progress/done observations after owner verification. Evidence declares
subject_sha, manifest and manifest_sha256; applicability remains explicitly
unverified until the owning BMad workflow checks the actual board/gate and
current source. The helper writes nothing and does not invoke that workflow.
A done entry never regresses. Starting a story lifts a backlog epic; comments and
all unrelated bytes remain unchanged. Missing epic, stale digest or ambiguous
source keys fail; an already-applied change returns an empty patch.
