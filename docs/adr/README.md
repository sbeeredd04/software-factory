# Architecture decisions

Canonical decision records live under `.software-factory/context/decisions/` in a full source checkout. The release archive excludes that repository context; use the full source when inspecting decisions or the current board. This index names the source files without copying their authority.

- Host-owned continuous orchestration (`.software-factory/context/decisions/0021-continuous-host-orchestration.md` in a full source checkout) defines the visible loop and scope for operations.
- Documented host contracts (`.software-factory/context/decisions/0022-documented-host-contracts.md` in a full source checkout) limits claims about invocation and isolation.
- Evidence-bound transitions (`.software-factory/context/decisions/0023-evidence-bound-transitions.md` in a full source checkout) binds protected board states to current receipts and decisions.
- Generated native distribution (`.software-factory/context/decisions/0024-generated-native-distribution.md` in a full source checkout) separates source skills and self-contained bundles.
- BMad module pins (`.software-factory/context/decisions/0025-bmad-module-compatibility-pins.md` in a full source checkout) records the approved official installer versions.
- Additive evaluation admission (`.software-factory/context/decisions/0026-additive-evaluation-admission.md` in a full source checkout) keeps case IDs and plan digests source-bound.
- Continuous delivery and risk-adaptive human decisions (`.software-factory/context/decisions/0027-risk-adaptive-continuous-delivery.md` in a full source checkout) supersedes unconditional per-epic human-stop prose while preserving evidence and reserved decisions.

Earlier records cover source/projection separation, installer ownership, recovery, review ingestion, overlays, offline validation and the public-clean release. Read the exact ADR before changing a settled contract.
