# Derived review-bot rules

Only owner-selected integrations are configured. Baseline config has no bots;
all four templates are inert source assets. Writing files neither activates a
subscription nor proves vendor access, effective rules or a successful review.
Pushing config can affect an already-enabled integration and needs appropriate
external-write authority. No credentials, vendor setup or services are installed.

## Four supported targets

- Greptile: `.greptile/config.json`, `rules.md`, `files.json`; new config disables
  automatic review triggers. Files references point to the existing four modules.
  Rules are markdown; structured user JSON is never lossy-rewritten.
- CodeRabbit: `.coderabbit.yaml` with `reviews.path_instructions`, each entry
  containing a glob and instructions. Never use removed `reviews.instructions`.
- Bugbot: `.cursor/BUGBOT.md` plus `.cursor/config/bugbot.yaml`, `version: 1` and
  Autofix disabled. Settings come from the PR **base branch**, not necessarily
  the repository default or PR head. Personal overrides can take precedence;
  fields can lower Autofix but cannot activate it above dashboard settings.
- Copilot: `.github/copilot-instructions.md`; optional scoped files under
  `.github/instructions/*.instructions.md` use `applyTo` frontmatter. The baseline
  renderer targets only the root file. Code review cannot follow external
  standards URLs from instructions; include derived approved text instead.

Sources: [Greptile fields](https://www.greptile.com/docs/code-review/greptile-config-reference),
[CodeRabbit fields](https://docs.coderabbit.ai/reference/configuration),
[Bugbot](https://cursor.com/docs/bugbot),
[Copilot instructions](https://docs.github.com/en/copilot/tutorials/customize-code-review).
All template files are under `integrations/bots/` in the source pack; the installer
projects them into this skill's templates directory. Never hand-edit projections.

## Plan, inspect, approve, apply

The config selects each bot via `review_bots.ID.enabled/config`; supported target
paths are fixed. `authors` is an optional exact GitHub login allowlist for triage.
Absent/empty authors means no vendor attribution. Examples such as
`greptile-apps[bot]`, `coderabbitai[bot]`, `cursor-ai[bot]` and `Copilot` must be
confirmed against the actual repository; custom factory/droid authors work too.
Nothing treats a comment author as authority.

Read all four approved `documents.principles` modules. Their paths and SHA256
hashes accompany each generated rule section and the proposal. A separate
source-linked principles decision and exact proposal approval are required:

```sh
python3 -I -B scripts/render_bots.py --project /project plan \
  --bots greptile coderabbit bugbot copilot \
  --principles-ref 'decision:approved-principles' > /private/bot-proposal.json
python3 -I -B scripts/render_bots.py --project /project apply \
  --proposal /private/bot-proposal.json --approved-sha REVIEWED_SHA256 \
  --decision 'decision:approved-bot-diff'
```

`plan` is the dry run: no lock, directories, backups or receipts. Its JSON includes
exact writes and unified proposed diffs for unsupported merges. Saving stdout is
an explicit caller action. Review those files before authorizing `apply`.
Approval references are supplied provenance; the host verifies actual owner
scope. Setup proposal/receipt version1 can supply context, but `sf-setup-reuse/1`
is explicitly not fresh approval. File existence or schema success is not approval.

Missing/empty/unsafe principles, stale sources or a changed plan digest refuse
before writing. Rules are derived text, not a second editable principles format.
The renderer refuses more than19,000 instruction characters rather than truncating
rules; CodeRabbit's individual instructions cap is20,000 and Bugbot ignores
settings files above64KB. Larger projects need a reviewed scoped projection.

## Preservation and recovery

Markdown prefixes/suffixes are byte-preserved. A managed section updates only
when its digest matches the prior receipt. Ambiguous/edited markers produce a
proposal. YAML refresh requires the entire non-whitespace document to be the
owned managed section; unmanaged surrounding YAML makes it proposal-only to
avoid duplicate keys or changed topology. User tone/path instructions remain
untouched. Complex Greptile
JSON receives a proposed diff, not an applied reserialization. Only selected
bots can change. Settings-only JSON provenance is kept in the receipt; rule
surfaces carry four-source provenance directly.

Apply rechecks sources/targets, uses the shared persistent install lock and
anchored no-follow publication. Original entries and receipts remain in private
`.software-factory/backups/` recovery directories (the reused lifecycle primitive
uses an `uninstall-` prefix). It never overwrites a new concurrent destination.
On failure it restores independent unchanged publications, retains contested
files/recovery copies, and reports manual reconciliation. Do not claim a
byte-identical whole-tree rollback: directories, lock and evidence may remain.
The bot receipt is written last. Repeating an unchanged plan makes no writes.
Installed/native helpers require their packaged templates and lifecycle helper;
missing assets fail closed instead of importing consumer ancestor code. Only
the canonical source layout uses top-level pack dependencies.

To inspect a configured Greptile's effective merged rules, its documented command
is `greptile config [PATH] --json`; dashboard/org settings participate. This is
manual, separately authorized vendor observation, never local presence detection
or a helper dependency. [CLI documentation](https://www.greptile.com/docs/code-review/greptile-cli).

No-bot setup is `not_applicable`. Missing gh blocks external actions, not local
work/proof/review. Required current-head bot reports gate only their own review
requirement. Helpers do not enable integrations or validate live subscriptions.
