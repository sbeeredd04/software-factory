# Technique index

66 techniques in six groups. "When" is the situation that justifies the move. Look up the smell map before picking one from memory.

## Composing methods

Long methods hide the logic. These moves name a piece or remove a name that hides nothing.

| Technique | When |
|---|---|
| Extract Method | A fragment hangs together and deserves a name. |
| Inline Method | The body is clearer than the name. |
| Extract Variable | An expression is hard to read in place. Do not split a short-circuit check that must not always run. |
| Inline Temp | A temporary holds a trivial expression and does not cache an expensive call. |
| Replace Temp with Query | A local's expression should be a named method. Keep the local if it caches a slow call. |
| Split Temporary Variable | One local is reused for unrelated values. Leave loop counters. |
| Remove Assignments to Parameters | The body writes into a parameter. |
| Replace Method with Method Object | Locals are too tangled to extract. This adds a class. Last resort. |
| Substitute Algorithm | The whole algorithm should be replaced with a clearer one, under the same tests. |

## Moving features

| Technique | When |
|---|---|
| Move Method | Another type uses the method more than the owner. |
| Move Field | Same, for a field. |
| Extract Class | One type has two reasons to change. Stop if the new type would be empty. |
| Inline Class | A type does almost nothing and nothing further is planned. |
| Hide Delegate | Callers dig through a nested object. Stop before every method is a forwarder. |
| Remove Middle Man | A type mostly forwards. |
| Introduce Foreign Method | One extra operation on a type you cannot change. |
| Introduce Local Extension | Several extra operations on a type you cannot change. |

## Organizing data

| Technique | When |
|---|---|
| Change Value to Reference | Many equal instances should be one shared object. |
| Change Reference to Value | A small rarely-changing shared object is not worth its lifetime. |
| Duplicate Observed Data | Domain data is trapped in a UI type. |
| Self Encapsulate Field | You need a hook on access. Otherwise direct access stays simpler. |
| Replace Data Value with Object | A field has grown its own data and behavior. |
| Replace Array with Object | One array mixes different kinds of slots. |
| Change Unidirectional Association to Bidirectional | Each side truly needs the other. Two-way links couple the types. |
| Change Bidirectional Association to Unidirectional | One direction is unused. |
| Encapsulate Field | A field is public. |
| Encapsulate Collection | Callers mutate a collection through a getter. |
| Replace Magic Number with Symbolic Constant | A bare number has a meaning. Skip numbers that are already obvious. |
| Replace Type Code with Class | A code never selects behavior. |
| Replace Type Code with Subclasses | A code selects behavior and the type is fixed at creation. |
| Replace Type Code with State/Strategy | A code selects behavior and subclasses do not fit. A small code does not need the extra types. In Python, strategy is often a function. |
| Replace Subclass with Fields | Subclasses differ only by constants they return. |

## Simplifying conditionals

| Technique | When |
|---|---|
| Consolidate Conditional Expression | Several conditions share one result. |
| Consolidate Duplicate Conditional Fragments | The same lines sit in every branch. |
| Decompose Conditional | The condition or the branches are too dense to read. |
| Replace Conditional with Polymorphism | The same type-based branch is copied. One dispatcher can stay a table of functions. |
| Remove Control Flag | A boolean exists only to steer later branches. |
| Replace Nested Conditional with Guard Clauses | Nesting hides the normal path. |
| Introduce Null Object | Callers keep testing for null. You pay with another type. |
| Introduce Assertion | A block assumes a condition. Use a handleable error if a caller must recover. |

## Simplifying method calls

| Technique | When |
|---|---|
| Add Parameter | The method lacks data it cannot already reach. |
| Remove Parameter | A parameter is unused, including in overrides. |
| Rename Method | The name does not say what it does. |
| Separate Query from Modifier | One method both answers and mutates. A command that reports a count can stay. |
| Parameterize Method | Several methods differ only by a value. Stop if the result is a long conditional or a flag. |
| Introduce Parameter Object | The same parameter group repeats. Give it behavior or it is a data class. |
| Preserve Whole Object | Callers strip an object into loose arguments. |
| Remove Setting Method | A field is set only at creation. |
| Replace Parameter with Explicit Methods | A parameter selects which body runs, and new variants keep appearing. |
| Replace Parameter with Method Call | The caller queries only to pass the result into a method that could query. |
| Hide Method | A method is unused outside its type. |
| Replace Constructor with Factory Method | Construction does more than store arguments, or the caller must pick a subtype. |
| Replace Error Code with Exception | A special return means failure. Do not use exceptions for ordinary control. |
| Replace Exception with Test | An exception is thrown where a check would do. |

## Generalization

| Technique | When |
|---|---|
| Pull Up Field | Subclasses declare the same field. |
| Pull Up Method | Subclasses do the same work. |
| Pull Up Constructor Body | Subclass constructors repeat setup. |
| Push Down Field | A superclass field is used by few subclasses. |
| Push Down Method | Superclass behavior is used by few subclasses. |
| Extract Subclass | Some features apply only in certain cases. Inheritance dead-ends when you later need two ways to vary. |
| Extract Superclass | Two types share fields and methods, and neither already has a parent. |
| Extract Interface | Clients share a slice of an API. This does not remove duplicated bodies. |
| Collapse Hierarchy | A subclass is effectively its parent. |
| Form Template Method | Subclasses run the same steps in the same order. Do this after the steps are real, not before. |
| Replace Inheritance with Delegation | A subclass uses only part of its parent. The cost is forwarding methods. |
| Replace Delegation with Inheritance | A type forwards almost every call and does not already have a parent. If it forwards only some, keep delegation. |

## Tidies — structure-only, before a behavior change

Tidies are the smallest allowed unit: structure-only moves, batched small and
reversible, and never in the same diff as a behavior change. Tidy first when a
little order unblocks the change; stop when the next behavior change is
unblocked, not when the file is pretty. The individual moves already live in
the catalog above: guard clauses, dead-code deletion, renames, extract and
inline.

## Architecture-scale moves

Three moves operate above the technique scale. The safety contract is
unchanged: pin current behavior first, adding a characterization or golden
test only where the seam has no pin; one move at a time with the tree
runnable; run the existing tests after each move and treat a red test as a bug
or an over-coupled assertion rather than weakening the pin; stop when the
named smell is gone; never ship a feature in the same change. A move that
crosses a module boundary writes or amends a decision record
([adr.md](adr.md)).

| Move | Shape |
|---|---|
| Strangler Fig | Incremental replacement behind a stable front door: route new work to the new implementation until the old one has no callers left. |
| Branch by Abstraction | A temporary seam in front of the old implementation lets callers migrate one at a time. |
| Parallel Change | Expand → migrate → contract: add the new path alongside, move the callers, then delete the old path in the same plan — a seam with no deletion date becomes a flag farm. |
