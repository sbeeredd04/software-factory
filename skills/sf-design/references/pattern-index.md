# Pattern index

22 catalog patterns. One line each: the problem that already has to be in the code, and the harm of adding it early. Classification is by intent. Scale is the other axis: an idiom is language-sized, a pattern is design-sized, an architectural pattern shapes the whole process. These 22 are design-sized.

History in one line: Alexander named patterns for buildings; Gamma, Helm, Johnson, and Vlissides named 23 object-oriented ones in 1994. This catalog teaches 22.

## Creational

- Factory Method. Callers need a product without naming the concrete type. Harm: a creator subclass per type before the set varies.
- Abstract Factory. A family of products must match, and callers must not see the concretes. Harm: a swarm of interfaces for a family you do not have.
- Builder. Construction has many ordered steps or several representations. Harm: a builder for a constructor that is still readable.
- Prototype. You must copy an object without depending on its class. Harm: clone machinery, especially with cycles, before copying matters.
- Singleton. The process truly has one instance. Harm: hidden coupling and tests that cannot substitute it. Prefer an argument.

## Structural

- Adapter. The right behavior has the wrong interface and you cannot change the source. Harm: a wrapper when you could have changed your own type.
- Bridge. One type varies on two independent axes. Harm: splitting a class that is still one responsibility.
- Composite. Clients should treat a part and a tree of parts alike. Harm: one interface forced onto operations that do not match.
- Decorator. Add behavior at runtime without a new subclass. Harm: an order-sensitive stack of wrappers.
- Facade. A complicated subsystem needs a small published entry. Harm: the facade absorbs the application's policy and becomes the god module.
- Flyweight. A huge number of near-identical objects will not fit in memory. Harm: shared-state machinery while memory is fine.
- Proxy. A stand-in must control latency, access, or a remote call. Harm: an extra hop before that control is needed.

## Behavioral

- Chain of Responsibility. More than one handler may take a request, and the set changes. Harm: a chain that drops work while the handlers were known.
- Command. An operation must be queued, retried, or undone. Harm: a class between caller and callee before you need any of those.
- Iterator. Clients walk a structure they should not know. Harm: heavier than a loop over a list.
- Mediator. Peers are too coupled to change alone. Harm: the mediator becomes the only place that knows everything.
- Memento. You need snapshots without exposing fields. Harm: snapshot volume and lifetime bookkeeping.
- Observer. Many subscribers must react, and the set changes. Harm: implicit order and a missed unsubscribe, where a direct call was enough.
- State. Behavior is a mode, and there are many modes that change often. Harm: a class per mode when a conditional is still obvious.
- Strategy. Algorithms are swapped. Harm: a class per algorithm. A function is the usual form.
- Template Method. Subclasses share an ordered algorithm and override steps. Harm: a frozen skeleton and subclasses that skip a step. Extract methods first. Share a template only after the steps match.
- Visitor. New operations over a stable set of types. Harm: every visitor changes when the type set changes. If the types change more often than the operations, do not use it.

Two technique pages are the supported way to arrive at a pattern: Replace Type Code with State/Strategy, and Replace Constructor with Factory Method. Do not start from the pattern page.
