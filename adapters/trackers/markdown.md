# Markdown tasks

Exact task syntax:

```text
- [ ] STORY-1: Foundation | ac: specs.md#ac1 | depends: -
- [x] STORY-2: Completed capability | ac: specs.md#ac2 | depends: STORY-1
```

IDs are explicit uppercase letters/digits/hyphens, stable across reordering and
renaming. Dependencies are comma-separated IDs without spaces or `-` for none;
AC references are comma-separated links. Duplicate IDs, unknown dependencies and
checkbox tasks without the documented fields fail. Other prose is preserved.

Observations never update the board. A completion proposal changes only the
exact task's checkbox, with the captured source digest and subject-bound manifest
references. The planning owner verifies current applicable proof and authority
before applying. No helper writes the source; completed entries never regress.
