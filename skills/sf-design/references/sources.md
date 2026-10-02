# Sources

Paraphrase the sources below. Do not copy their prose into a review or a skill.

## Refactoring.Guru

Process: [refactoring](https://refactoring.guru/refactoring), [what refactoring is](https://refactoring.guru/refactoring/what-is-refactoring), [when](https://refactoring.guru/refactoring/when), [how](https://refactoring.guru/refactoring/how-to), [technical debt](https://refactoring.guru/refactoring/technical-debt).

Smells: [index](https://refactoring.guru/refactoring/smells). Each smell lives at `https://refactoring.guru/smells/<slug>`. Group pages live under `/refactoring/smells/`. `/refactoring/smells/<slug>` 404s.

Techniques: [index](https://refactoring.guru/refactoring/techniques). 6 groups, 66 techniques, each at `https://refactoring.guru/<slug>`.

Patterns: [index](https://refactoring.guru/design-patterns), [what](https://refactoring.guru/design-patterns/what-is-pattern), [why](https://refactoring.guru/design-patterns/why-learn-patterns), [classification](https://refactoring.guru/design-patterns/classification), [catalog](https://refactoring.guru/design-patterns/catalog), [history](https://refactoring.guru/design-patterns/history), [criticism](https://refactoring.guru/design-patterns/criticism). 22 GoF patterns in the catalog (the 1994 book lists 23).

## Books and essays

- Martin Fowler, [*Refactoring*](https://martinfowler.com/books/refactoring.html) (1999; 2nd ed. 2018). Smell names and the technique catalog.
- Joshua Kerievsky, *Refactoring to Patterns* (2004). A pattern is where a refactor arrives, not where it starts.
- Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides, [*Design Patterns*](https://en.wikipedia.org/wiki/Design_Patterns) (1994). The names. The Gang of Four.
- Michael Feathers, *Working Effectively with Legacy Code* (2004). Find a seam, pin behavior with tests, then move.
- Ward Cunningham, OOPSLA 1992. Debt is a loan, and interest is the extra cost of change.
- Martin Fowler, "[Technical Debt Quadrant](https://martinfowler.com/bliki/TechnicalDebtQuadrant.html)". Reckless vs prudent, deliberate vs inadvertent.
- David Parnas, "On the Criteria to Be Used in Decomposing Systems into Modules" (1972). One module hides one decision. That is divergent change, stated earlier.
- Robert C. Martin. Single responsibility means one reason to change.
- Craig Larman, GRASP. Information Expert: behavior sits with the data it uses. Feature envy is the expert in the wrong place.
- Bertrand Meyer. A query returns a value. A command changes state. Do not mix them without a reason.
- Kent Beck, *Test-Driven Development*. Refactor is the third step, under a test that already passes.
- Paul Graham, "Revenge of the Nerds." Many patterns patch a language that lacks a function, a macro, or a closure. The criticism page cites this.
- Christopher Alexander, *A Pattern Language* (1977). The idea the Gang of Four borrowed: a named solution you adapt, not a template you copy.
