# BMad Method v6 planning

BMad skills and structured epics/stories are central to the delivery method.
The installer uses the official BMad Method **6.12.0** path, with
**tea=v1.27.2**, **bmb=v2.2.2** and **cis=v0.3.2**. ADR 0025 (`.software-factory/context/decisions/0025-bmad-module-compatibility-pins.md` in a full source checkout)
records the decision; [the provisioning reference](../skills/software-factory/references/bmad-provisioning.md)
and [installer source](../scripts/bmad_install.py) own the exact command sequence.

Provisioning requires Node >=20.12 and `node`, `npm`, `npx`, `uv` and `git`.
It may download packages, so review its external boundary separately from
local `--skip-bmad` installation. The [installation guide](installation.md)
begins with the offline local route. Missing prerequisites produce a degraded
result and instructions; the installer does not install tools globally or use
sudo. Existing or partial BMad trees are preserved for inspection. Do not
erase them or silently retry a failed provisioning attempt.

Record the observed module versions and actual generated planning source before using it. Version tags and transitive dependencies are not a cryptographic immutable lock. A successful install only proves provisioning, not the quality of a generated plan, live host loading or an approved work item. The [tracker adapter](../adapters/trackers/bmad-v6.md) maps accepted planning into the board. The Markdown adapter can represent an explicitly scoped alternative, but a missing BMad planner is recorded as unavailable rather than silently simulated. Independent plan review and evidence gates still apply.
