# Staff the work by evidence and risk

The eleven `sf-*` roles are starting prompts, not a mandatory fleet. The orchestrator keeps one owner for the loop and staffs only the expertise the risk and task need. Every worker returns its actual subject/diff, commands, results, uncertainty and next action. Independent reviewers inspect the actual work, and the integration owner reconciles claims before merging. The [canonical team map](../skills/software-factory/references/team.md) owns routing detail.

| Work | Useful starting roles |
| --- | --- |
| Intent, scope and architecture | `sf-product-manager`, `sf-architect`, `sf-design-reviewer` |
| Standard feature or defect | `sf-engineer`, `sf-ai-engineer`, `sf-principal-engineer` as complexity warrants |
| Proof and risk review | `sf-qa-engineer`, `sf-evaluator`, `sf-code-reviewer`, `sf-security-reviewer` |
| Integration and release | `sf-release-engineer` |

One worker can fill multiple low-risk implementation tasks, but cannot independently approve its own change. Sensitive installer, state, auth or policy work needs deeper review. Optional model routes are proposed from observed host capabilities by [sf-agents](agents.md); a null presence or denied permission stays a gap. The host records requested and observed effective models separately. A claim is path ownership evidence, not process liveness.
