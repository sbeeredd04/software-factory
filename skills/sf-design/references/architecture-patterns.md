# Architecture patterns

One entry per pattern: the problem that must already be measured in the code,
the first measured signal, when not to adopt, and the lighter move to prefer.
Treat each pattern the way the pattern index treats a GoF pattern: adopt only
when its measured problem is present, and every adoption writes a decision
record ([adr.md](adr.md)) and wires a check ([fitness-functions.md](fitness-functions.md)).
A healthy architecture report is mostly "absent on purpose."

## Modular monolith

- Measured problem: cross-module imports grow unowned inside one deployable, and a split is being discussed.
- First signal: boundary enforcement (dependency and visibility rules) exists and is green; a boundary nothing checks is a folder.
- When not: not sufficient only when the microservices preconditions below are already measured.
- Lighter move: this is the lighter move — enforced module boundaries inside one deployable come before any second deployable.

## Layered

- Measured problem: a request path crosses presentation, domain and data code with no enforced direction.
- First signal: zero upward imports under a declared layer contract.
- When not: a thin CRUD app does not earn four layers, and a layer whose rule nothing detects fills with business logic within a few years.
- Lighter move: two or three layers with an enforced direction beat four unenforced ones.

## Hexagonal / ports and adapters

- Measured problem: the app cannot run without its UI or database, so automated tests, batch drivers and program-to-program calls are blocked, or a third-party edge is genuinely substitutable.
- First signal: count secondary ports with exactly one production adapter and no second implementation; a high count is ceremony, not substitutability.
- When not: a thin CRUD app, where a repository interface per table plus a use case per endpoint costs more than the coupling it prevents.
- Lighter move: keep ports few and purpose-based (two to four), one adapter per port until a second is real.

## CQRS

- Measured problem: inside one bounded context, a measured read/write load divergence, or a domain the single model demonstrably cannot serve.
- First signal: the read side is the measured bottleneck, and a reporting database or read replica was tried first.
- When not: system-wide or by default; most systems are CRUD-shaped, and a second read model means two models to keep consistent.
- Lighter move: a read replica or reporting database before a second read model.

## Event-driven

- Measured problem: name which of the four meanings is in play — notification, event-carried state transfer, event sourcing, CQRS. They are different patterns with different costs.
- First signal: a sender that needs the recipient to act is a command, not an event; count events that are passive-aggressive commands.
- When not: when the cross-system flow must stay visible; with notification the flow exists only in monitoring. Any flow spanning more than three notifications gets a decision record, because it is invisible in code.
- Lighter move: direct calls or commands until the decoupling is measured as needed; event sourcing only where audit or replay is a stated requirement, with a record.

## DDD, strategic only

- Measured problem: one model stretched across several business areas — a shared mega-model.
- First signal: bounded contexts are named with one model per context; aggregates protect true invariants only, stay small, reference each other by identity, and one transaction touches one aggregate with eventual consistency across.
- When not: the tactical zoo (a repository per aggregate, domain-event plumbing) before a context has earned it.
- Lighter move: name the contexts and their ownership first; tactical patterns only inside a context that needs them.

## Microservices

- Measured problem: the coordination premium is already being paid — at least two teams need independent deploy cadence, and the dependency and co-change data prove the boundaries stable.
- First signal: enforced module boundaries in the monolith are green, and the split candidates sit exactly on those boundaries.
- When not: as a starting shape; systems built as microservices from scratch mostly end in trouble, and boundaries drawn early are usually wrong.
- Lighter move: a modular monolith with enforced boundaries; extract a service only at an edge the enforcement data proves real, with automated deploy, observability and contract tests already in place.

## Micro-frontends

- Measured problem: multiple teams own disjoint user-facing areas on genuinely different release trains. The bar is team topology, not bundle size.
- First signal: cross-team release coordination is the measured cost.
- When not: a small app or a small team — you pay duplicated dependencies, consistency effort and operational overhead for coordination you do not have.
- Lighter move: route and module boundaries inside one build.
