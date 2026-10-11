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
uvx --from ruff==0.17.0 ruff check .       # Python lint (pinned; keep in sync with CI)
npx -y shellcheck@latest install.sh        # shell lint (runs when install.sh exists)
python3 scripts/validate.py               # canonical layout and frontmatter rules
python3 scripts/scan_public.py             # public-cleanliness scan (private terms, secrets, paths)
python3 scripts/check_links.py             # relative-link resolution
python3 skills/sf-eval/scripts/sf_eval.py run --plan evals/eval.config.json --mode premerge  # the pack's own evals
```

It also runs the Agent Skills spec validator
(`uvx --from skills-ref agentskills validate skills/<name>`) on every skill, schema checks
(`uvx check-jsonschema`) on the GitHub workflows and issue forms, and renders every Mermaid
diagram (network-dependent). The script itself is the authoritative, ordered list.

## The pack dogfoods itself

This repository runs on the method it ships. Its committed project-context home is
`.software-factory/context/`: the principles modules under `principles/`, the `CODEBASE.md`
crawl artifact, the master board under `board/` (per-story records plus the regenerable
`roadmap.json` and `dashboard.html`), and the decision records under `decisions/`. Its own
eval plan is `evals/eval.config.json`, and the gate above runs it on every change. After
board record changes, regenerate the projections with
`python3 skills/software-factory/scripts/roadmap.py build`; after source changes, regenerate
the crawl artifact with `python3 skills/sf-crawl/scripts/crawl.py .`. Both are checked for
freshness by the eval suite.

For a quick inner loop, run the narrow checks directly:

```bash
python3 -m unittest discover -s tests -v
uvx --from ruff==0.17.0 ruff check .
```

CI runs the same gate on Linux and macOS across Python 3.11 to 3.13 on every push and pull
request (see `.github/workflows/ci.yml`).

## File budgets

The pack gets leaner as it grows: every shipped file stays inside a stated budget. The caps
live here and as named constants at the top of `scripts/validate.py`; the gate checks every
class and fails on a breach, printing the cap beside the measured value, and a clean run
prints the current maximum per class.

| File class | Cap | Measured maximum (2026-10-11) |
| --- | --- | --- |
| Entry skill (`skills/software-factory/SKILL.md`) | 150 lines | 138 |
| Non-entry skill (`skills/<name>/SKILL.md`) | 120 lines | 86 (`sf-smell-audit`) |
| Role agent (`agents/sf-*.md`) | 60 lines | 28 |
| Frontmatter `description` | 300 characters | 296 |
| Frontmatter keys | canonical keys only (`name`, `description`, `license`, `compatibility`, `metadata`; agents `name`, `description`, `model`) | - |
| Prose reference (any non-entry Markdown under `skills/`) | 240 lines | 195 (`references/recovery.md`) |
| Data/catalog/index reference | 320 lines | 127 (`references/technique-index.md`) |

Every cap carries headroom above the measured maximum on purpose; a cap that sits exactly on
today's largest file is a broken cap. If your change needs more room, split the file
(progressive disclosure) or raise the cap here and in `scripts/validate.py` in the same
commit, with the new headroom stated.

Reference files belong to exactly one class. A reference file is data/catalog/index exactly
when its file name is listed in `REFERENCE_DATA_FILES` in `scripts/validate.py` - today
`technique-index.md`, `pattern-index.md`, `smell-technique-map.md`, `sources.md`, and the
`questions.md` interview bank that ships with the onboarding milestone. Every other
non-entry Markdown file under `skills/` (references and workflows) is a prose reference.
Adding a new catalog, index, map, or question-bank file means adding its name to that
constant.

One neighboring rule is deliberately not in this table: decision records (ADRs) under
`.software-factory/context/decisions/` carry their own 40-line document-length rule. That is
a per-record writing discipline, not a reference-file cap, and it is enforced separately.

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
   (progressive disclosure). Every file stays inside its class budget - see
   [File budgets](#file-budgets).
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
