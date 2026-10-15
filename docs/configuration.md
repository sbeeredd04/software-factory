# Configuration

The installed `.software-factory/config.yaml` uses a JSON-compatible YAML subset, version 1. The [canonical reference](../skills/software-factory/references/configuration.md) and [schema](../schemas/config.schema.json) define accepted keys. The installed `config.py` validates both schema shape and semantic references; it does not execute configured commands.

Start with the [grounded onboarding proposal](onboarding.md). Its selected product, conventions, risk and eval principle documents should already exist or be explicitly drafted. The proposed config is a draft until the host reviews the exact source digest and decision. An example project's [config fixture](../examples/config/config.yaml) illustrates structure; its synthetic signoff is not a consumer approval.

```sh
"$SF_PYTHON" -I -B "$SF_KERNEL/config.py" validate --config "$SF_PROJECT/.software-factory/config.yaml" --root "$SF_PROJECT"
```

Run this after setup applies. A missing document, unsupported key, invalid branch policy or malformed value is a failed validation, not a reason to weaken the schema. Resolve it in the governing document or approved proposal and retry. Keep principle paths project-relative and bound to the actual chosen documents.

The config records a tracker adapter, integration branch and optional parallel ceiling. The host observes real capacity and permissions before staffing; a configured ceiling cannot create available workers. BMad planning is the primary structured route; unavailable capability must be
reported, and any alternative needs actual applicable scope and equivalent proof. Optional integrations and monitoring require actual scope, access and authority. The [tracker contract](../skills/software-factory/references/trackers.md) explains BMad v6, Markdown and the v7 stub; neither a config label nor a draft planning file is a live tracker transition.
