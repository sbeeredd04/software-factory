# Local distribution and release artifacts

The source root exposes eleven canonical skills through Agent Plugins 1.0
`plugin.json` and `skills/`. This portable route is **skills-only**. Full project
setup, BMad provisioning and lifecycle management use `install.py install`.
Native bundles add projected host invocation policies and recovery hooks without
creating consumer settings, pointers, runtime state or home configuration.

## Bootstrap

Use Python 3.11 or newer and a local checkout for offline setup:

```sh
sh /path/to/software-factory/install.sh --host all --skip-bmad --dry-run
```

The caller's current directory is the default project. An explicit `--project`
is forwarded unchanged, including spaces. A sibling `install.py` always selects
the local checkout, even with `--ref`. No download occurs on that route.

A standalone `install.sh` uses the documented default `v0.1.0`, or `--ref TAG`.
It downloads `sf-TAG.tar.gz` and `SHA256SUMS` from
`https://github.com/sbeeredd04/software-factory/releases/download/TAG/`.
This is the configured public artifact destination, not a statement that a
release has been published. No latest lookup or fallback occurs.

The trusted bootstrap verifies SHA-256 before extraction or installer execution.
It rejects ambiguous checksums, traversal, links, devices, collisions, oversized
archives (128 MiB total decoded tar bytes, including metadata and padding;
10,000 entries) and missing installers. Before tarfile parses the archive, a
bounded decompression pass and raw header scan reject PAX/GNU extension headers
and data hidden after the archive terminator. Releases use the USTAR format
with explicit regular-file/directory types; legacy NUL/V7 types are rejected
to keep raw scanning and tarfile payload boundaries identical. The raw scan
uses tarfile's fixed-header parser for size and checksum semantics; it never
invokes extension-payload processing. Downloads
use HTTPS, bounded transfer size/time and disposable private staging cleaned on
normal completion or handled failure. Forced process termination can leave OS
temporary files. Checksums from the same origin provide integrity checking,
not an independent publisher signature. Python launches use `-I -B` to ignore consumer module paths/startup overrides
and suppress bytecode writes, including child installer and hook processes.
No runtime is installed automatically.

## Generate native marketplace roots

```sh
python3 install.py project --host claude-code --out /existing/parent/new-bundle
python3 install.py project --host all --out /existing/parent/new-bundles
python3 scripts/check_distribution.py
```

The output must be absent, have an existing parent, and contain no symlink path
components. Use resolved absolute temporary paths on systems with `/tmp` aliases.
Output may be external or under ignored `dist/`; generated files are never
committed. Generation builds from canonical source, does not install BMad, and
removes incomplete output on handled failures. Repeated generation uses two new
output directories; compare bytes, paths and modes.

A single-host output is a marketplace root containing `plugins/software-factory`
and its catalog. `all` creates one marketplace root per host:

- Claude: `.claude-plugin/marketplace.json`; native manifest inside the plugin.
- Cursor: `.cursor-plugin/marketplace.json`; native manifest inside the plugin.
- Codex: `.agents/plugins/marketplace.json`; portable manifest inside the plugin.

Catalog sources resolve relative to each marketplace root. Component paths
resolve within each plugin root. Claude and Cursor package eleven native role
prompts. Codex packages eleven generated TOML roles under `role-prompts/` for
manual/reference use: plugin custom-agent registration remains unverified.
Use the project installer for custom agents. Permissions inherit the parent
session; reviewer prose does not enforce an independent read-only sandbox.

Hook commands use documented `${CLAUDE_PLUGIN_ROOT}`, `${CURSOR_PLUGIN_ROOT}`,
and `${PLUGIN_ROOT}` expansion. The bundled launcher validates consumer `python3`
>=3.11 and fails softly with a sanitized recovery warning if unavailable. It
reads consumer paths from hook input (`cwd`, or Cursor's single `workspace_roots`
entry), never from the build machine. Ambiguous multi-root Cursor input produces
a recovery warning. Hooks are inert without an active program and do not start
workers. Codex hooks require explicit user trust. Avoid enabling overlapping
project and plugin hook installations; duplicate recovery is not a tested mode.

Local format checks and fixture hook execution do not prove live host loading,
marketplace acceptance or publication. Hook-bearing OpenAI plugins are currently
excluded from the public plugin directory; local/manual use is a distinct route.
Combined Cursor/Codex shared-frontmatter tolerance remains unverified.

## Local release assembly

```sh
python3 scripts/build_release.py --ref v0.1.0 --out /existing/parent/new-release
```

The reviewed `hosts/plugins/release-files.json` allowlist defines the source
payload; new source files require an explicit allowlist update. Native projectors
read a disposable snapshot of those captured bytes, so unlisted local files and
changes made after capture cannot enter the generated release payload. Generated native
marketplaces are included at `dist/plugins/<host>/`. Git metadata, private project
context, runs, caches and receipts are excluded. Archive ordering, ownership,
timestamps and modes are normalized; `SHA256SUMS` describes the final bytes.
This command only builds files locally. It does not publish, push or deploy.

## Canonical skills CLI route

The separate network-marked fixture records the CLI version, lists local skills,
and installs into a disposable Git repository with all three explicit hosts:

```sh
DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 npx -y skills@1.7.2 add /path/to/software-factory --list
DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 npx -y skills@1.7.2 add /path/to/software-factory -a claude-code -a cursor -a codex -y
```

This checks eleven canonical skill names/descriptions, `.claude/skills`, shared
`.agents/skills`, `skills-lock.json`, and absence of `.cursor`/`.codex` output.
CLI-created links are legitimate; this does not establish native roles, hooks
or invocation policy. `SF_SKIP_NETWORK=1` skips this check as unverified.
No host agent CLI is executed; fixture guard stubs prove that boundary.

## Format sources

Contracts inspected 2026-10-15:

- [Agent Plugins 1.0 schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json),
  vendored unchanged as `schemas/plugins/portable.schema.json` for offline checks;
  upstream Apache-2.0 attribution and license details are recorded in `NOTICE.md`.
- [Claude manifest and variables](https://code.claude.com/docs/en/plugins-reference)
  and [marketplaces](https://code.claude.com/docs/en/plugins/marketplaces).
- [Cursor plugins](https://cursor.com/docs/reference/plugins) and
  [hook inputs](https://cursor.com/docs/hooks).
- [OpenAI packaging, marketplaces and hooks](https://developers.openai.com/plugins/build/plugins).
- [Vercel skills CLI](https://github.com/vercel-labs/skills).
