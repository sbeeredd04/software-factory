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

## Architecture patterns and decision records

- Alistair Cockburn, "[Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture)" (2005). The original ports-and-adapters article: run without UI or database, and the unenforced-layer failure mode.
- Martin Fowler, "[Monolith First](https://martinfowler.com/bliki/MonolithFirst.html)" (2015). Service splits pay only after the coordination premium is real; early boundaries are usually wrong.
- Martin Fowler, "[CQRS](https://martinfowler.com/bliki/CQRS.html)" (2011). Per-bounded-context only; a reporting database first; many adopters were harmed.
- Martin Fowler, "[What do you mean by 'Event-Driven'?](https://martinfowler.com/articles/201701-event-driven.html)" (2017). The four conflated meanings and the passive-aggressive-command trap.
- Cam Jackson, "[Micro Frontends](https://martinfowler.com/articles/micro-frontends.html)" (2019), and Colin Eberhardt, "[You probably don't need a micro-frontend](https://blog.scottlogic.com/2021/02/17/probably-dont-need-microfrontends.html)" (2021). Team topology is the bar; enforced module boundaries in one build are the lighter move.
- Vaughn Vernon, "[Effective Aggregate Design](https://www.dddcommunity.org/library/vernon_2011/)" (2011). Small aggregates, true invariants only, reference by identity, one transaction per aggregate.
- Michael Nygard, "[Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)" (2011, CC0). The origin: numbered records, monotonic, superseded never deleted.
- [MADR 4.0.0](https://adr.github.io/madr/) ([repo](https://github.com/adr/madr), MIT OR CC0). The maintained section skeleton, including the confirmation section.
- Red Hat, "[Why you should be using architecture decision records](https://www.redhat.com/en/blog/architecture-decision-records)" and [The GDS Way](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decision-record.html). Mainstream adoption evidence.

## Measurement and enforcement

- Neal Ford, Rebecca Parsons, Patrick Kua, *Building Evolutionary Architectures* (2nd ed., [O'Reilly](https://www.oreilly.com/library/view/building-evolutionary-architectories/9781098274896/); [InfoQ overview](https://www.infoq.com/articles/fitness-functions-architecture/)). Fitness functions as runnable integrity checks.
- Adam Tornhill, "[Code as a Crime Scene](https://www.adamtornhill.com/articles/crimescene/codeascrimescene.htm)" ([book](https://pragprog.com/titles/atcrime2/)). Hotspots as churn × complexity; temporal coupling above ~30% over a 2–3 month window.
- John Ousterhout, [*A Philosophy of Software Design*](https://web.stanford.edu/~ouster/cgi-bin/book.php) (2018). Deep vs shallow modules; interface size versus hidden implementation mass.
- Robert C. Martin, package principles (ADP/SDP/SAP; [summary](https://fi.devpub.com/reference/ppp-the-stable-dependencies-principle)). No cycles; depend toward stability; I = Ce/(Ce+Ca).
- Enforcement tools, named per ecosystem and never installed by the pack: [import-linter](https://import-linter.readthedocs.io/) and [grimp](https://grimp.readthedocs.io/) (Python), [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) and [eslint-plugin-boundaries](https://github.com/javierbrea/eslint-plugin-boundaries) (TS/JS), [ArchUnit](https://www.archunit.org/) (Java), [packwerk](https://github.com/Shopify/packwerk) (Ruby, with the [Shopify retrospective](https://railsatscale.com/2024-01-26-a-packwerk-retrospective/) and [enforcement write-up](https://shopify.engineering/enforcing-modularity-rails-apps-packwerk)).

## Extended smells, tidies, and architecture-scale moves

- [Code Smells Catalog](https://luzkan.github.io/smells/) and its academic anchor, "[Code Smells: A Comprehensive Online Catalog and Taxonomy](https://link.springer.com/chapter/10.1007/978-3-031-25695-0_24)" (Springer, 2022). Provenance for the second-catalog rows; paraphrase, never import the taxonomy wholesale.
- Kent Beck, [*Tidy First?*](https://www.pragmaticbookshelf.com/titles/beck-tidy/) (2023). Structure-only tidies, batched small, never mixed with a behavior change.
- Martin Fowler, "[Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)" and "[Branch by Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)". The architecture-scale moves; parallel change is their expand → migrate → contract sibling.

## Modern stacks and the agent era

- [Stack Overflow Developer Survey 2025, AI section](https://survey.stackoverflow.co/2025/ai). Falling trust, "almost right" output as the top frustration — the case for measure/pin/verify and shallow-free interfaces.
- [GitHub Octoverse 2025](https://octoverse.github.com/). TypeScript's rise on AI-assisted workflows; types as machine-checkable guardrails.
- Serverless granularity: [AWS Well-Architected Serverless Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html), [organizing larger serverless applications](https://aws.amazon.com/blogs/compute/best-practices-for-organizing-larger-serverless-applications/), and the [Lambdalith practitioner case](https://rehanvdm.com/blog/should-you-use-a-lambda-monolith-lambdalith-for-your-api/).
- FastAPI [dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) and [testing with overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/). The framework's DI is the wiring; overrides are the test seam.
- LLM code smells (candidate-grade, first formal catalogs): "[Specification and Detection of LLM Code Smells](https://arxiv.org/abs/2512.18020)" and the extended "[LLM Code Smells: A Taxonomy and Detection Approach](https://arxiv.org/abs/2605.22976)". Early and still growing; watch item, not stable catalog.
