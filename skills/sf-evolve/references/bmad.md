# BMad customization and finite delegation

This guidance targets BMad Method 6.12.0, with separately pinned tea 1.27.2,
bmb 2.2.2 and cis 0.3.2. Observe the actual installation manifest before relying
on it. Missing or unsupported versions keep customization unknown and leave the
factory's native fallback available. The pack never vendors BMad's resolver.

## Installed fields govern the proposal

Read the target skill's installed `customize.toml`. Make sparse team changes in
`_bmad/custom/<skill>.toml`; personal `<skill>.user.toml` remains gitignored and
is never rewritten by the factory. Preserve unrelated keys and existing IDs.
Do not edit rendered skills, base customization or installer-owned central files.
Generic hooks include `activation_steps_prepend`, `activation_steps_append` and
`persistent_facts`; workflow completion can expose `on_complete`. Propose absent
knobs instead of inventing them. `implementation_handoff` is specific to
supporting build workflows; `review_layers` belongs to supporting build/review
workflows and `lenses` to `bmad-review`. Confirm each installed field.

The source for this placement and field guidance is the pinned
[BMad customization guide](https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/v6.12.0/docs/customize/customize-bmad.md).
These are supported upstream concepts, not proof that this consumer ran them.

## Static merge preview

Layers apply base, then team, then personal. Scalars replace; nested tables merge
recursively. Uniformly `code`- or `id`-keyed arrays replace matching whole items
in place and add new identities; other arrays append. Thus a keyed item override
must retain the complete intended item, and an append is not a deletion.
The read-only helper previews these shapes without calling the official resolver.
See the pinned [merge implementation](https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/v6.12.0/src/scripts/config_utils.py).

```sh
python3 skills/sf-evolve/scripts/evolve.py bmad-inspect --root <project> --base .claude/skills/bmad-build/customize.toml --changes evidence/sparse-change.json
```

The optional changes file is a JSON object of sparse proposed keys. No TOML is
written. Unsupported fields, observed versions and callback field names are
reported with captured source hashes. Existing team/personal keys are preserved
in the preview. Missing packaged metadata parser or schema dependencies fail
rather than guessing a source-checkout ancestor.

## Prevent recursive ownership

Before a BMad invocation owned by the factory, inspect effective base, team and personal
hooks, completion and implementation handoff. Record a finite delegation boundary:
the requested artifact, one responsible owner, the return point and how retries
stop. Reject a completion/handoff that invokes the factory again while it owns
the run. Preserve unrelated user customization; propose a scoped revision to the
recursive route rather than silently disabling review or changing personal files.

The helper flags literal factory callbacks and conservatively leaves all dispatch
permission with the host, including indirect routes it cannot understand. An
unknown effective customization or callback is a gap to resolve before dispatch.
A static TOML parse is not resolver proof, and even a resolver output cannot
establish execution safety of arbitrary callback prose. The host must inspect
actual tools and scoped authority. The upstream resolver is optional; using its
usual uv path can provision Python, so this helper never invokes it or any agent
CLI. Record actual resolver verification separately if independently authorized.
