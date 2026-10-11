# The case contract

Every case carries: a stable `id` of the shape `<SURFACE>-<STORY>-<NN>`
(e.g. `FE-CART-001`, `BE-CART-002`), the `story` and `epic` it belongs to,
the `suite` and `surface` that grade it, the `criterion` text it was
derived from, its `kind` (`fail_to_pass` or `pass_to_pass`), its `grade`
rung, the run `tier` list that includes it, and a `nondeterministic` flag
(with `trials` and a consistency policy when set). The runner validates
this shape and fails closed on a malformed case.

## Kinds

- `fail_to_pass`: must newly pass once the story is implemented.
- `pass_to_pass`: already passes and must keep passing — regression cover
  from earlier stories and epics.

## ID stability

IDs are unique across the plan and stable across regenerations: drafting
the plan twice from the same input yields the same ID set, with no
renumbering. A retired case's ID is never reused for a different case.

## Two-way traceability

A story is not done until its case IDs are green, and every case cites the
criterion it enforces: a story's acceptance criteria and its cases are the
same mechanism. Case IDs are what receipts, gate manifests and the story's
board record cite — never prose summaries.

## Balanced sets

Every behavior gets its negative or error-direction case wherever that
direction is meaningful — invalid input, unauthorized, out of stock — not
only the happy path. A one-sided set produces one-sided optimization.

## Satisfiability

Every `fail_to_pass` case must be demonstrably satisfiable: either setup
sketches the intended observable outcome ("with a correct implementation
this passes because …"), or the case carries an explicit first-green
verification flag so its first pass is reviewed as proof the case can be
satisfied. A case that no correct implementation can satisfy is a broken
case: route it as an eval-fix, never a code-fix — see the routing rules in
[modes](modes.md).
