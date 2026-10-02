---
name: sf-patterns
description: "Judges whether a Gang of Four design pattern belongs, or whether it would be speculative generality. Use when the user asks about design patterns, Strategy, Factory, Singleton, Facade, or whether to add a pattern during a refactor."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: design
  release: v0.1
---

# Design pattern judgment

A pattern is a named blueprint you adapt. It is not a requirement. The criticism that matters: patterns often patch a missing language feature, people copy the class diagram literally, and a freshly learned catalog makes every problem look like a nail.

Index: [../sf-design/references/pattern-index.md](../sf-design/references/pattern-index.md).

## Decide

Answer these in order. Stop at the first no.

1. Is the problem already in the code (a repeated switch, a clump, two axes of change, a subsystem callers should not see)? If you are designing for a future variant, this is speculative generality. Do not add the pattern.
2. Does the language already say it? In Python a swappable algorithm is a function. A queued operation can be a closure. A factory can be a function. Use the class form only when you need several methods or a place to store state that the function cannot close over cleanly.
3. Will the pattern become the smell it is famous for? Facade and Mediator become a god module. Singleton hides the dependency and fights tests. Template Method freezes a skeleton the subclasses will fight. Visitor must change whenever the element set changes.
4. Is there a refactoring technique that arrives at this pattern? Prefer that path. Replace Type Code with State/Strategy and Replace Constructor with Factory Method are the two that name a pattern. The others should stay techniques.

## Fits that are usually real

- Adapter on a third-party client you do not control.
- Observer when many listeners subscribe and unsubscribe, and a direct call list would be edited every time.
- State when modes are numerous and behavior changes with the mode. A handful of flags is still a conditional.
- Facade when it is the published edge and it stays thin. The moment it holds the policy, it is divergent change.

## Fits that are usually early

- Abstract Factory, Visitor, Flyweight, and a class-per-command layer, unless the audit already showed the pain.
- Singleton for something that can be an argument.
- Bridge before a class is actually varying on two axes.

## Report line

For each pattern you mention, one line: present, absent on purpose, or harmful if added. A healthy catalog is mostly "absent on purpose."
