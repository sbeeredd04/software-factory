# Verification and evidence


Start from accepted assertions and the actual user outcome. Keep a negative case
for the new behavior and regression proof for existing behavior. The canonical
[sf-eval skill](../skills/sf-eval/SKILL.md) owns case/grade shapes and the local
[configuration contract](../skills/software-factory/references/config-schema.md)
owns configuration. Do not copy another grader or schema into the manual.

## Plans and exact subjects

A consumer eval plan needs its real applicable source-linked decision and digest.
A shipped example or setup eval draft does not supply that approval. Fixture
approval records are synthetic and never impersonate an independent owner.
Use the same canonical payload rule when cases change and review affected cases.

Once an actual approved plan exists, these are the helper's literal commands.
Use the installed skill path chosen for your host in [smoke-test](smoke-test.md).
Replace the story key with the exact `story` value in that plan:

```sh
SF_STORY_KEY='demo/greet-name'
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-eval/scripts/sf_eval.py" run --plan "$SF_PROJECT/evals/eval.config.json" --mode quick --story "$SF_STORY_KEY" --project-root "$SF_PROJECT"
```

The runner writes actual run/case receipts and failure artifacts. Inspect the
printed outcome and actual receipt location; a process exit0 alone is not the
asserted effect. A red/unverified result is retained and repaired, not renamed.
For a real resulting receipt, substitute its actual path:

```sh
SF_RECEIPT='/absolute/path/to/actual/evals/receipt.json'
"$SF_PYTHON" -I -B "$SF_SKILLS/sf-eval/scripts/sf_eval.py" verify --receipt "$SF_RECEIPT"
```

Self-hash verification establishes integrity. It does not authenticate the caller,
validate every semantic claim, make stale subjects current or supply actual human
acceptance. An override is a separately approved recorded decision preserving
prior results; it is not a quickstart way to turn failure into success.

## Independent proof and transition ownership

Keep candidate SHA, independent actual-diff review, integrated SHA, observed artifact
identity/environment and affected behavior distinct. A claim assigns paths; it does
not prove a worker runs. The orchestrator uses existing board transition/gate
contracts, not manual edits to generated roadmap/dashboard/graph files.

Required built/done transitions verify current evidence and applicable checkpoint
provenance. Source hashes/names are structural provenance, not authenticated owner
identity or observed remote effects. Unknown integration or effect proof remains
a gap. A reserved human checkpoint still requires its real source-linked decision.
Where delegated epic acceptance is applicable, its scope and evidence must be
explicit and distinct from a recorded human decision.
See the canonical [evidence contract](../skills/software-factory/references/evidence.md).

## Conditional epic acceptance

The orchestrator assesses consequences throughout planning, implementation,
integration, effect proof and recovery. A material unknown or owner reservation
escalates the affected dependents while independent authorized work can continue.
At epic acceptance, `autonomy.mode: risk-adaptive` and
`checkpoints.manual: false` permit the delegated route only if epic `hitl` is
false and no applicable story reservation remains. An absent mode or manual
profile uses the human route. Neither mode nor a completed child list grants
acceptance by itself.

For an authorized delegated route, the configured standing delegation identifies
the exact `sf-epic-delegation/1` grant bytes and source: finite named epic IDs,
`accept-epic`, owner identity, aware time and optional expiry. The separate
`sf-consequence-assessment/1` binds the current epic scope, config, risk
principles, grant and review evidence. Its acceptance decision is `proceed` with
no reservations, unknowns or blocked dependents; permission, effect, recovery
and risk states are `authorized`, `pass`, `bounded` and `resolved`. The independent
review bundle binds the consequence assessment digest as well as exact current
child outcomes. An accepting owner or reviewer cannot be an implementation owner.

With the [quickstart helper paths](quickstart.md#preview-and-install) set, the
orchestrator first sets `SF_EPIC_ID`, `SF_OWNER`, `SF_GRANT`, `SF_ASSESSMENT` and
`SF_REVIEW` to actual reviewed values. The last three are workspace-relative
contained files, not sample approvals. Its protected transition then uses:

```sh
"$SF_PYTHON" -I -B "$SF_KERNEL/roadmap.py" epic --workspace "$SF_PROJECT" \
  --epic "$SF_EPIC_ID" --actor orchestrator --status done --owner "$SF_OWNER" \
  --delegation "$SF_GRANT" --assessment "$SF_ASSESSMENT" --evidence "$SF_REVIEW"
```

This page supplies no grant or decision. The `--decision` flag is for the
separate human acceptance path. A delegated record says `by: orchestrator` and
`mode: delegated`, retaining actor and bindings; it never impersonates a human.
The [exact delegated evidence contract](../skills/software-factory/references/evidence.md)
defines the assessment digest rule and refusal cases. Helper validation checks
structural provenance, not actual owner identity or the truth of an assessment.

## Describe only the proof performed

Static host/config/resource checks do not prove live host loading, a separately
enforced sandbox, browser media effects or publication. Synthetic DOM/clipboard
adapters can demonstrate a code regression without proving real clipboard bytes.
Native UI observations name their exact source, engine, viewport and settings;
manual motion-off is not native reduced-motion emulation. A separately prepared
browser method does not become execution proof or permission merely by existing.

The repository's actual native feature/bug/review/recovery history belongs in
[DOGFOOD](DOGFOOD.md) with retained failures and exact subjects. A bounded synthetic newcomer
scenario can prove preservation, deduplication, no-fix/recovery and authority
separation; it is not a real production incident or an independently signed
consumer acceptance. Local staging equivalence, maintainer integration and final
publication retain their applicable owner decisions.
