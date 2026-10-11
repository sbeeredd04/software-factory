# Conventions — Software Factory

## Coding conventions

- Shipped code is Python >= 3.11, standard library only. No third-party
  imports, no install step, no virtual environment, no network or model
  calls in shipped helpers.
- Tests are `unittest` under `tests/`; shared fixtures in
  `tests/fixtures/`; network-dependent tests skip on `SF_SKIP_NETWORK=1`.
- One canonical source per artifact: skills and agents are hand-edited
  once; host projections are generated, never hand-edited.
- Conventional commits with generic, public-clean wording.
- The gate is `bash scripts/check_all.sh`; run it before every handoff and
  report real commands and exit codes, never claimed results.

## The design and anti-bloat bar

- Reuse first: extend the existing owner of a rule in place; never restate
  it in a second location.
- The smallest complete diff: no unrequested abstraction, no speculative
  generality, no drive-by changes outside the story.
- Deleting the obsolete path is part of done, not a follow-up.
- One runnable check per story: every change lands with the test, case or
  command that proves it.
- Budgets are enforced: entry skill 150 lines, non-entry skills and agents
  at their stated caps, descriptions 300 characters, reference files per
  their cap class. New content absorbs or compresses before it adds.
