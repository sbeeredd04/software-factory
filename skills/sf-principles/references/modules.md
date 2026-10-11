# The four principles modules

Exactly four modules live under the configured principles paths (default
`.software-factory/context/principles/`). Every configured path must exist
and be readable; a missing, empty or unreadable module is a blocked state
reported with its path — never a silent default, never guessed content.

| Module | Must contain |
| --- | --- |
| `product.md` | What the product is for, the outcomes that matter, explicit non-goals. |
| `conventions.md` | The coding conventions plus the design and anti-bloat bar: reuse first, the smallest complete diff, no unrequested abstraction, obsolete-path deletion as part of done, one runnable check per story. |
| `risk.md` | The risk tiers, the named human owner, and the actions that always escalate to a human decision rather than being decided by an agent: production writes; money, auth, state-machine, migration or concurrency changes; destructive operations on user work; policy or security change; credential or trust change; publishing. |
| `evals.md` | The eval policy: eval-first, per-surface suites, the deterministic-first grading ladder, the judge rules, and the override rules. |

## Authoring and editing

Each module is user-authored: the skill interviews (user answers plus the
crawl's `CODEBASE.md` and discovery facts), proposes a draft, and the user
approves it before any judgment relies on it. Edits work the same way — a
principles change is proposed, never applied by a skill or a module. A
principle the code contradicts is recorded as a finding with its evidence
(path, count or command) and a confirmed/unconfirmed marking, never silently
overridden; during onboarding, a user answer that conflicts with a detected
convention escalates with a recommendation instead of resolving silently.

## Reading the principles

Every skill or role that needs the principles carries this two-line section
with identical wording wherever it appears, and links the configured paths
rather than restating them:

> Read the repository's own governing principles; they remain authoritative.
> Do not create a second format.

If a principle forbids or mandates a pattern, the principle wins with no
re-derivation — record the application of the principle, not a fresh
decision. If a recorded decision conflicts with the principles, stop and
surface the conflict to the human owner named in `risk.md` with a
recommendation; the resolution is written as a superseding decision record,
and a change to the law itself is a proposed principles edit.
