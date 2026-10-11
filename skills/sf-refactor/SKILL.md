---
name: sf-refactor
description: "Chooses refactoring techniques and a safe order of moves for a smell that was already measured. Use when the user asks how to refactor, which technique to apply, or how to pay down technical debt without a rewrite."
license: MIT
compatibility: Works with Claude Code, Cursor and Codex.
metadata:
  factory-role: design
  release: v0.1
---

# Refactoring playbook

Use after `sf-smell-audit`. The audit names the smell. This skill picks the move and the order. It does not add behavior.

Technique names and the when-not rules live in [../sf-design/references/smell-technique-map.md](../sf-design/references/smell-technique-map.md). The 66-technique index is [../sf-design/references/technique-index.md](../sf-design/references/technique-index.md).

## When a refactor is the job

Rule of three: the third copy is the refactor. Also when the change you need cannot be made safely inside the mess, and when a bug sits in a method you cannot read. A dedicated cleanup of a healthy module is not the job.

Tidies — small structure-only moves — are the smallest allowed unit before a behavior change, batched small and reversible, and they never travel in the same diff as the behavior change.

## Safety

1. Pin the current behavior with the tests that already exist. Add a characterization test only where a seam has no pin. Feathers: seam first, then move.
2. One technique at a time. The tree stays runnable.
3. Run the existing tests after the move. A red test is either a bug you introduced or a test that was coupled to a private helper. Replace the private assertion with a higher-level one. Do not weaken the pin.
4. Do not ship a feature in the same change.
5. Stop when the smell you named is gone. Do not tour the catalog.

## Order for a bloated orchestrator

This is the usual shape when one function acquired every new branch:

1. Introduce Parameter Object or Preserve Whole Object for the clump that is repeated on the signature. The object must be the thing the code already passes around, not a new framework type.
2. Extract Method along the existing phases (validate, one turn, one side effect, finalize). Names come from those phases.
3. Extract Class or extract a module only where a second reason to change is already in the function. Divergent change is that signal. A long but single-purpose procedure gets methods, not a new package.
4. Replace the copied switch with a map of functions once two call sites branch on the same set of names. One call site can keep a straight sequence.
5. Delete the dead parameter and the speculative hook you passed through and never read.

## Debt

Pay interest where change is already slow: the module everyone edits, the seam that shows up in dozens of files. Do not open a rewrite. Delayed refactoring is the cause that compounds, because new code keeps calling the obsolete part.

Quadrant, used as a label not a score: prudent-deliberate debt was a known loan; prudent-inadvertent debt is a design you can see only after the code taught you; reckless debt skipped a seam you already knew how to make. Repay prudent debt in the module that owns it. Reckless debt still gets the same techniques, with a test pinned first because the seam was never there.

## Architecture-scale moves

The index's three architecture-scale moves — Strangler Fig, Branch by Abstraction, Parallel Change — run under the same safety contract above: pin first, one move at a time with the tree runnable, tests green after each move, stop when the named smell is gone, and never ship a feature in the same change. Two bars are added: a move crossing a module boundary writes or amends a decision record, and a Parallel Change deletes the old path in the same plan rather than leaving a permanent seam. Shapes: [../sf-design/references/technique-index.md](../sf-design/references/technique-index.md).

## Reject

- A base class for packages that happen to share filenames, before the steps are the same. That is Form Template Method too early, and it creates the hierarchy smell.
- A strategy class per branch in a language with first-class functions.
- Comment deletion as the project. Rename and extract, then the narration comment has nothing left to say.
- A new abstraction layer that forwards every call. That is Middle Man.

## Project principles

Read the repository's own governing principles; they remain authoritative.
Do not create a second format.
