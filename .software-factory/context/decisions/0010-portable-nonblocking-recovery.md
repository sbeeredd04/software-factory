# 0010 — Portable nonblocking recovery with explicit hook trust

Status: accepted · 2026-10-11

## Context

Sessions compact, crash and resume. Hooks differ per host: Cursor cannot
block pre-compact; Codex requires explicit hook trust and hooks may not
execute.

## Drivers

- Durable notes must not become an instruction-injection route.
- A recovery pointer is context, never new authorization.

## Options

- Stop-hook infinite continuation: hostile to the user and the host.
- Inline the entire checkpoint as privileged context: injection-prone.
- Session start emits a bounded factual pointer; pre-compact captures
  observations and never blocks.

## Outcome

Recovery is a small pointer plus durable notes at meaningful transitions,
with host adapters encoding each event shape, because that is the
strongest semantic every host can actually honor.

## Consequences

- No resurrection or reset-survival promise; no raw transcript capture.
- Untrusted or unsupported hooks degrade to manual checkpoint/resume.
- Codex hook trust is a user action after install; doctor reports it as
  user-confirmation-required.

## Confirmation

- `tests/test_hook.py` covers the envelopes, inert behavior and sanitized
  warnings; host formats are validated statically.
