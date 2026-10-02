# Contributing to Software Factory

Thanks for helping build the factory. This page covers setup, the verification gate, the
conventions every change follows, and the fold-in path for new skills.

Questions and proposals: open an issue using one of the forms under `.github/ISSUE_TEMPLATE/`
(bug report, feature request, or skill and integration contribution).

## Setup

You need Python >= 3.11 and git. That is the complete list: no sudo, no global installs, no
virtual environment, no dependencies. Everything the pack ships is standard-library Python.

```bash
git clone https://github.com/sbeeredd04/software-factory.git
cd software-factory
python3 -m unittest discover -s tests -v
```

Development and validation tools (ruff, check-jsonschema, shellcheck, the Mermaid renderer, the
Agent Skills validator) run on demand through `uvx` and `npx`; they are never installed into
your environment. Node.js >= 20 is needed only for the npx-based checks, and only when you run
them.

## The verification gate

Run the full gate before every pull request and every handoff:

```bash
bash scripts/check_all.sh
```

`scripts/check_all.sh` is the authoritative gate. Its core steps:

```bash
python3 -m unittest discover -s tests -v   # unit tests (SF_SKIP_NETWORK=1 skips network-marked tests)
uvx ruff check .                          # Python lint
npx -y shellcheck@latest install.sh        # shell lint (runs when install.sh exists)
python3 scripts/validate.py               # canonical layout and frontmatter rules
python3 scripts/scan_public.py             # public-cleanliness scan (private terms, secrets, paths)
python3 scripts/check_links.py             # relative-link resolution
```

It also runs the Agent Skills spec validator
(`uvx --from skills-ref agentskills validate skills/<name>`) on every skill, schema checks
(`uvx check-jsonschema`) on the GitHub workflows and issue forms, and renders every Mermaid
diagram (network-dependent). The script itself is the authoritative, ordered list.

For a quick inner loop, run the narrow checks directly:

```bash
python3 -m unittest discover -s tests -v
uvx ruff check .
```

CI runs the same gate on Linux and macOS across Python 3.11 to 3.13 on every push and pull
request (see `.github/workflows/ci.yml`).

## Conventions

- **Commits.** Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
  with generic, public wording.
- **Branches.** Never push directly to `main`, and never force-push. Feature branches target
  the integration branch: open pull requests against `dev`; a maintainer merges `dev` to
  `main`.
- **Public-clean.** This repository is published open source. No private project names, people,
  absolute user paths, credentials, or private product decisions in any file or commit
  message. Generalize private experience; never paste it. `scripts/scan_public.py` enforces a
  denylist.
- **Shipped code.** Standard-library Python (>= 3.11) only, with `unittest` tests under
  `tests/`. No third-party imports, no model calls, no network calls in shipped code.
- **Honesty.** Documentation claims only behavior that was verified, and states limitations
  plainly. Report the commands you ran and their real results.
- **Style.** Skills and role prompts are agent-first: direction, focus, context, and evidence
  expectations - not rigid scripts or prohibition lists. See [AGENTS.md](AGENTS.md).

## Adding a skill to the factory

There are two fold-in paths:

**At runtime (your project).** Install the pack and use the `sf-evolve` skill. It registers the
skill in `.software-factory/config.yaml`, writes an overlay that survives reinstalls, and runs
the retro -> proposed patch -> independent review -> tested apply pipeline. Your factory
improves without hand-patching.

**In this repository (for everyone).**

1. **Location.** Create `skills/<name>/SKILL.md`. The folder name must equal the frontmatter
   `name`. Keep the entry short and put detail in `references/` files linked from it
   (progressive disclosure).
2. **Frontmatter.** Use only the standard keys: `name`, `description` (trigger-first, at most
   300 characters), `license`, `compatibility`, and `metadata` (string values only).
   Host-specific fields (for example, Claude-only argument hints) belong to the projection
   layer, never to canonical files.
3. **Scripts.** Any deterministic helper is standard-library Python (>= 3.11) with `unittest`
   tests under `tests/`. Helpers never call models, change Git, or touch the network.
4. **Validate.** Run the skill-spec validator, the layout validator, and the full gate:

   ```bash
   uvx --from skills-ref agentskills validate skills/<name>
   python3 scripts/validate.py
   bash scripts/check_all.sh
   ```

5. **Docs.** Update the skills list in [README.md](README.md), the relevant `docs/` page, the
   orchestrator reference under `skills/software-factory/references/` if the orchestrator
   should dispatch to the new skill, and [CHANGELOG.md](CHANGELOG.md).

To propose a skill or integration without implementing it, open a "Skill or integration
contribution" issue - the form carries the same checklist.
