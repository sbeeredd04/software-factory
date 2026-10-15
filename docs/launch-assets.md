# Regenerating and using launch assets

The repository contains seven committed PNG masters rendered from original
HTML/CSS/SVG templates. The showcase serves byte-identical copies of its three
cards directly from `site/img/`; viewing the site needs no build step. The release
archive includes the README hero. Regeneration is a repository development task,
not an installer prerequisite or a consumer runtime feature.

## Explicit developer preparation

Use a supported POSIX machine with Python >=3.11, `uvx`, and the operating-system
prerequisites for the pinned Playwright Chromium build. The preparation below
downloads developer packages and a browser into a cache you choose. It does not
install system packages or fonts. No global tool installation is needed.

```sh
export SF_RENDER_CACHE="$(mktemp -d)"
export SF_RENDER_EVIDENCE="$(mktemp -d)"
export UV_CACHE_DIR="$SF_RENDER_CACHE/uv"
export PLAYWRIGHT_BROWSERS_PATH="$SF_RENDER_CACHE/browsers"
export UV_PYTHON_DOWNLOADS=never
export PLAYWRIGHT_SKIP_BROWSER_GC=1
uvx --python python3 --from playwright==1.64.0 \
  --with greenlet==3.5.6 --with pyee==14.0.0 \
  --with typing_extensions==4.16.0 playwright install --only-shell chromium
```

Keep those cache/evidence settings for later regeneration. The evidence directory
must be private, owned by you and outside the source checkout. Each run retains
its bounded raw browser launch log there for review; only sanitized launch flags
and a log hash enter the public receipt. The command prints the private run path
and reports failures concisely rather than dumping raw browser stderr.
Failed captures retain a bounded readiness, resource and request diagnostic in
that private log before the browser context closes.
`assets/toolchain.json` pins
the package versions and Chromium headless shell revision 1248 / 156.0.8078.4.
Missing OS prerequisites require explicit developer setup; the renderer does not
install them or retry with a disabled sandbox. Native Windows execution is not
established by this POSIX helper.

## One regeneration command

From a full source checkout, after the explicit preparation above:

```sh
python3 scripts/render_assets.py
```

The standard-library entry point starts a bounded local job. A small optional
developer helper imports Playwright inside an isolated, pinned, offline uv tool
environment. The helper is excluded from consumer releases. It launches a new
temporary Chromium profile with the sandbox explicitly enabled, and inspects the
actual launch arguments. It does not attach to your browser, change proxy settings
or grant permissions. Only the unnecessary unsafe SwiftShader opt-in is removed
from Chromium defaults. A missing or unsafe launch record fails the run.

The renderer snapshots only the finite public input allowlist and serves it on
127.0.0.1. Browser requests are restricted to that origin, service workers are
blocked, and a restrictive content policy applies. Offline uv prevents package
downloads; it is not itself a browser network sandbox. Each template must load all
four named font faces, decode images and fit its fixed canvas before capture.
Every output PNG is validated before any committed output is replaced.

## Output inventory

- `assets/social-preview.png` — 1280 × 640, manual repository social preview.
- `assets/hero.png` — 1600 × 900, README overview.
- `assets/loop.png` — 1200 × 800, delivery loop and repair path.
- `assets/team.png` — 1200 × 800, eleven roles grouped by responsibility.
- `assets/hosts.png` — 1200 × 800, three hosts and installation routes.
- `assets/launch-landscape.png` — 1200 × 675, landscape launch-post attachment.
- `assets/launch-portrait.png` — 1080 × 1350, portrait launch-post attachment.

The renderer exports loop, team and hosts into `site/img/` from the validated
master bytes. The manifest records every copy; their SHA-256 hashes must match.
The templates share the showcase's local fonts and palette. `assets/SOURCES.md`
and `site/fonts/SOURCES.md` record original artwork, immutable font sources and
licenses. No vendor marks are needed.

## Review and publication

Inspect every final PNG at its full dimensions and normal reading scale. Check
crop margins, small text, all eleven role names, repair arrows and host caveats.
Serve `site/` and inspect the three below-fold cards at narrow and wide viewports;
confirm the README hero resolves from the source tree and release archive.

```sh
python3 -m unittest discover -s tests -p test_assets.py -v
python3 -m http.server 4317 --bind 127.0.0.1 --directory site
```

`assets/render-receipt.json` contains input/output hashes, dimensions, observed
font readiness, requests, browser version and sanitized launch flags. Hashes
identify this render. Repeatable regeneration does not promise byte-identical
PNGs across operating systems or browser updates. Static fixture tests do not
establish actual browser or visual effects.

To set a repository social preview, a maintainer manually uploads
`assets/social-preview.png` in the repository's social-preview settings after
review. The two launch-post images are attachments for an explicitly approved
announcement. Rendering does not upload images, post messages, enable Pages or
publish a release. Keep the pre-release label until actual publication is known.

## Failure and recovery

Missing cache/browser, resource errors, font fallback, layout overflow, timeout,
unsafe launch arguments or an invalid PNG abort before output publication. All
previous outputs remain untouched in those cases. The command prepares the
complete set before replacing individual files and publishes its receipt last.

File replacement is atomic per file. A handled publication failure rolls back
only files whose identity and bytes still match this run's published output.
Foreign edits are preserved and recovery backups are retained for inspection.
Prepared new files and backups also have their identity and bytes checked before
moving, restoring or cleaning them. Contention retains a private recovery map
alongside the launch logs; a final comparison checks the published set.
Cooperating renderers share a directory lock; it does not lock human editors.
There is no globally atomic transaction across `assets/` and `site/img/`, nor a
promise of crash recovery after SIGKILL, power loss or failed rollback I/O.
If recovery is contested, preserve `.sf-asset-*` files and compare them with the
receipt before a maintainer reconciles the set. Do not delete unrelated files.

SIGTERM enters the bounded cleanup path with private log retention. The outer
process terminates and reaps its owned child process group; the helper's normal
unwinding closes its browser and Playwright driver. The ordinary Python fixture
proves that process-group path only. Detached browser descendants require actual
run observation; no universal orphan-free cleanup is claimed. SIGKILL cannot run
the cleanup path. Cleanup is limited to owned server, process and job resources.
The explicitly prepared developer cache remains available for the next run.
