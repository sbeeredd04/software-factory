# Factory evolution

The existing `sf-evolve` skill supports source-pinned capability metadata,
reviewed persistent Markdown overlays, sparse BMad customization proposals and
an evidence-led retro workflow. It adds no daemon, model client or new status
ledger. Start with the [skill](../skills/sf-evolve/SKILL.md), then choose the
[registry](../skills/sf-evolve/references/registry.md),
[overlay](../skills/sf-evolve/references/overlays.md),
[BMad](../skills/sf-evolve/references/bmad.md) or
[retro](../skills/sf-evolve/references/retro.md) contract.

The stdlib helper inspects and proposes; `install.py` remains the only publisher
of generated factory files. Registry source, payload, review and canary bytes
are hash-bound. A changed upstream base or edited target yields a conflict.
Reinstall reapplies valid overlays once, and uninstall preserves user-owned
sources and evidence. Supported overlays are generated skill entries/references;
entry frontmatter, governing documents, scripts and host policy are protected.

Validation establishes structural provenance, not authentic human consent or
host permission. Routine work needs an applicable reconciled GO; material policy,
security, trust, credentials, money and external changes need a named human
source decision. Third-party metadata never installs a skill or connects MCP.
BMad inspection is a static preview, not live agent or resolver execution proof.
The host reviews the real evidence and later authorized behavior before retention.

With the [quickstart helper paths](quickstart.md#preview-and-install) set, the
installed read-only registry entry is:

```sh
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-evolve/scripts/evolve.py" registry --root "$SF_PROJECT"
```

An empty registry is a valid result. A real overlay proposal needs its reviewed manifest and captured generated base; `evolve.py propose --root PROJECT --manifest RELATIVE --base RELATIVE` compares them without publishing. The host checks source, canary and review, then the installer owns any authorized overlay transaction.
