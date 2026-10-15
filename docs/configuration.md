# Configuration

The installed `.software-factory/config.yaml` uses a JSON-compatible YAML subset, version 1. The [canonical reference](../skills/software-factory/references/configuration.md) and [schema](../schemas/config.schema.json) define accepted keys. The installed `config.py` validates both schema shape and semantic references; it does not execute configured commands.

Start with the [grounded onboarding proposal](onboarding.md). Its selected product, conventions, risk and eval principle documents should already exist or be explicitly drafted. The proposed config is a draft until the host reviews the exact source digest and decision. An example project's [config fixture](../examples/config/config.yaml) illustrates structure; its synthetic signoff is not a consumer approval.

```sh
"$SF_PYTHON" -I -B "$SF_KERNEL/config.py" validate --config "$SF_PROJECT/.software-factory/config.yaml" --root "$SF_PROJECT"
```

Run this after setup applies, using the [quickstart helper paths](quickstart.md#preview-and-install). A missing document, unsupported key, invalid branch policy or malformed value is a failed validation, not a reason to weaken the schema. Resolve it in the governing document or approved proposal and retry. Keep principle paths project-relative and bound to the actual chosen documents.

The config records a tracker adapter, integration branch and optional parallel ceiling. The host observes real capacity and permissions before staffing; a configured ceiling cannot create available workers. New setup proposes `planning.method: bmad`, `autonomy.mode: risk-adaptive`, local edits and commits within GO, and `checkpoints.manual: false`. Push, PR, integration merge and deploy remain disabled until their actual scope is authorized. Existing profiles remain intact; an absent mode keeps legacy supervised epic acceptance.

BMad planning is the primary structured route. Missing, partial or unsupported BMad is a readiness gap, not an automatic switch: native planning needs explicit `planning.method: native`, a scoped fallback decision, or a preserved approved legacy route. A tracker label or draft file does not prove a BMad workflow ran. The [planning contract](../skills/software-factory/references/planning.md) and [tracker contract](../skills/software-factory/references/trackers.md) define those boundaries.

Risk-adaptive mode itself grants no epic acceptance. A configured manual checkpoint, epic `hitl: true`, required story reservation or governing owner decision still requires a human. Delegated acceptance additionally needs a current finite owner grant, exact scope and config/risk bindings, an independent consequence assessment and review, and passing child/effect gates. The [authority contract](../skills/software-factory/references/authority.md) and [evidence contract](../skills/software-factory/references/evidence.md) specify the exact fields. Optional integrations and monitoring require actual scope, access and authority.
