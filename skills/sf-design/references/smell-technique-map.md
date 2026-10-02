# Smell to first move

Health in an audit is 5 when the smell is absent and 1 when it owns the tree. The first move is the usual technique. Skip it when the "Do not" line is the actual situation.

Guru's detection bar, separate from severity: a method past about ten lines, a parameter list past three or four. Report both the count past that bar and the tail (300 lines, 10 parameters). The tail is the debt. The bar is the smell.

| Smell | First move | Do not |
|---|---|---|
| Long Method | Extract Method | Replace Method with Method Object unless locals are too tangled to extract. That adds a class. |
| Large Class | Extract Class, by reason to change | Extract Subclass when the split is a rare case, not the whole job. In procedural code, extract a module. |
| Primitive Obsession | Replace Data Value with Object | A type-code class when the code selects behavior. That case wants subclasses or a strategy function. |
| Long Parameter List | Introduce Parameter Object, or Preserve Whole Object | Add Parameter. The list is already the smell. |
| Data Clumps | Introduce Parameter Object that owns behavior | A bag of fields with no operations. That is a new data class. |
| Switch Statements | A registry of functions, then Replace Conditional with Polymorphism only if the same branch set is copied | A class per branch when there is one dispatcher. |
| Temporary Field | Extract Class for the algorithm that uses the field | A field left optional "so we might need it." |
| Refused Bequest | Replace Inheritance with Delegation | A new subclass to hold the unused methods. |
| Alternative Classes with Different Interfaces | Rename Method, then Extract Superclass only for the shared slice | A shared base that also merges unrelated behavior. |
| Divergent Change | Extract Class so each reason to change has a home | Splitting a class that changes for one reason. |
| Shotgun Surgery | Move Method and Move Field back together | Inline Class when the pieces are different reasons to change. That recreates divergent change. |
| Parallel Inheritance Hierarchies | Move Method so one tree absorbs the paired behavior | A third hierarchy "to unify" the two. |
| Comments | Extract Method and Rename Method | Deleting comments that record a real invariant. Replace those with a name or an assertion. |
| Duplicate Code | Extract Method. Pull Up Method only inside a real hierarchy | Form Template Method before the steps are actually the same. |
| Data Class | Move Method onto it if behavior is scattered | Forcing behavior into a boundary DTO. A DTO at a socket is allowed. |
| Dead Code | Delete it | A deprecation flag that keeps the dead path callable. |
| Lazy Class | Inline Class | Inlining a type that is the seam tests use. |
| Speculative Generality | Collapse Hierarchy, Inline Class, Remove Parameter | Deleting a seam that already has a second implementation. |
| Feature Envy | Move Method to the data | Moving a method that coordinates several objects. That coordinator may be the right owner. |
| Inappropriate Intimacy | Move Method or Extract Class; make a two-way link one-way | Hide Delegate on every call until the owner is a middle man. |
| Incomplete Library Class | Introduce Foreign Method for one operation | A local extension hierarchy for one missing call. |
| Message Chains | Hide Delegate once, or Move Method | A chain of facades. |
| Middle Man | Remove Middle Man | Removing the one facade that is the published API. |

Group meanings, in short: bloaters grew and were never cut; object-orientation abusers use objects halfway; change preventers make one idea cost many edits; dispensables are cheaper gone; couplers either know each other's insides or forward so much they know nothing.
