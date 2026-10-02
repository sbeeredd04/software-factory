# Hosts

Phase: host differences — what changes when the same factory runs on Claude
Code, Cursor or Codex.

The canonical skill you are reading is host-neutral. The installer projects it
into each host's format; fix the canonical source, never a generated copy.

## Invocation

- Claude Code: `/software-factory <plain request>`
- Cursor: `/software-factory <plain request>`
- Codex: `$software-factory <plain request>`

There is no required verb, menu or slug on any host. A trailing word like
`resume` is just part of the plain request.

## Hooks

On all three hosts the installer wires a session-start hook (a short recovery
pointer when a run is active, silent otherwise) and a pre-compact hook (refreshes
the snapshot). Host differences that matter:

- Cursor's pre-compact hook is observe-only; treat it as a snapshot trigger.
- Codex hooks take effect only after the user trusts them in the host; until
  then recovery relies on the human invoking the skill.
- When Cursor and Claude Code projections coexist in one project, the hook
  wiring suppresses duplicate recovery output.

Hooks and prompts are conveniences, not security boundaries; nothing in the loop
relies on them for safety.

## Staffing differences

Each host offers different machinery for employing agents — built-in subagent
mechanisms, separately configured agent CLIs, or none at all. The orchestrator
uses whatever the host and the project's `agents` configuration actually
provide, and the native host worker (doing the work directly, or through the
host's own subagents) is the always-available fallback. Where a host capability
is unverified, report the gap or keep the work under explicit supervision rather
than assuming it.

Models are requested, never assumed: record what was requested, and record the
effective model when the host reports it. Which models an account may use is
resolved by the host at dispatch time, never probed by the factory.

## Honest limits

The pack is validated statically and by fixture, not by live runs inside every
host. The documentation's capability matrix states what is verified per host;
prefer `unverified` over a confident guess, and tell the human when a step
depends on host behavior the pack has not been able to prove.
