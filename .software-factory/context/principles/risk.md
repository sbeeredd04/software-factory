# Risk — Software Factory

Human owner: the repository maintainer. Assess the actual work, affected assets,
blast radius, reversibility, requested autonomy and current authority at each
material phase. Reuse a source-linked GO covering the same scope. Escalate an
unresolved consequential decision with a recommendation; block its dependents
while continuing independent authorized work (ADR 0027).

## Risk tiers

- **Tier 0 — docs, prose, tests, fixtures.** Small spec, relevant proof.
- **Tier 1 — standard implementation.** Skills, scripts, tooling; the
  normal loop with its eval cases.
- **Tier 2 — sensitive mechanics.** Installer transactions, hook wiring,
  gate logic, state/lock handling, anything touching user files or
  settings; principal-engineer staffing and independent review.
- **Tier 3 — irreversible or outward-facing.** Publication, releases,
  history changes; require human GO covering the actual action and effect.

## Always escalate to the human owner

- Production writes without explicit GO covering the target and effect.
- Unresolved material effects on authentication, money, data integrity,
  migrations or concurrency; routine fixes within an approved outcome still
  require appropriate independent review and proof.
- Destructive effects on user work or history outside explicit authority.
  Force-pushes remain forbidden by repository policy.
- Changes to owner-reserved policy, permissions, hook trust or gate rules
  outside the accepted decision; an existing scoped approval is reusable.
- New credentials, access scopes or external services without scoped consent.
- Public repository visibility, releases or announcements without scoped GO.
- Principle conflicts, missing authority, unbounded recovery, unknown important
  effects, or an explicit human reservation. Never infer approval from silence.

Routine authorized work continues through epics with current evidence,
independent review and a recorded consequence assessment under finite delegation.
Adaptive mode grants no permission and removes no explicit story/epic reservation.

Tier scales ceremony — eval floors, review depth, checkpoint strictness —
and never removes the floor.
