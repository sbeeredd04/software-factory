# Patterns on the default stacks

One verdict line per pattern on the stacks consumers actually build with.
Verdicts use the `sf-patterns` report line — present / absent on purpose /
harmful if added — plus the fourth measured value `already provided by
<framework>`, allowed only where the framework's provision is named and
measured. `sf-patterns` reads this file; these verdicts are not added to the
pattern index.

## React / Next

- Strategy: already provided by React — a function, a prop or a hook is the swappable algorithm; a class per algorithm is harmful if added.
- Observer: present only with genuinely varying subscriber sets (`useSyncExternalStore`, signals); a direct call list is the default.
- Provider: already provided by context; a god-provider that everything reads is the divergent-change smell — count its consumers.
- Singleton: harmful if added — module-scope mutable state is shared across requests under SSR, a correctness bug, not a pattern. Bar: count module-level mutable assignments.
- Factory and Command: usually absent on purpose — a function or a closure carries them.
- Template Method: already provided by the framework's component lifecycle; do not re-implement it inside components.

## FastAPI / Flask / Django

- Dependency injection: already provided by FastAPI `Depends` or the app factory — construction wiring is a framework feature, so Singleton and Service Locator are harmful if added. Bar: hidden construction inside handler bodies.
- Test seam: already provided by dependency overrides — tests swap dependencies declaratively.
- Repository: present only with a second implementation or a real test seam; an interface per table with one implementation is the single-adapter ceremony. Bar: ratio of single-implementation interfaces.
- Value objects: already provided by Pydantic models.

## Postgres / Redis

- Transaction boundary: one per request; a transaction spanning a queue or cache write is the measured defect.
- Cache-aside: present only with a measured hit rate and a named invalidation owner — a cache without an invalidation path is a stale-data smell.
- CQRS-lite: a read replica or reporting database before a second read model (see [architecture-patterns.md](architecture-patterns.md)).

## Serverless

- HTTP APIs: one routed function (a "Lambdalith") is the legitimate default — the code stays a normal modular app, while per-route functions pay cold starts and config sprawl.
- Event handlers: single-purpose functions fit.
- Module-level mutable state: harmful if added — module scope is shared across invocations, and state lives outside the compute unit. Bar: count module-level mutable assignments.
- Handlers: idempotent, because retries are duplicates.

## Agent-era notes

- Wide, shallow wrappers are what makes generated code unreviewable: an agent
  that must justify a deep module writes less code you cannot check. Prefer
  deep modules — a small interface over real behavior.
- Types are the reviewable contract layer AI-assisted work selects for; treat
  the type error as the first fitness function.
- The first question before any new class: does the framework already provide
  this pattern? If yes, name the provision and stop.
