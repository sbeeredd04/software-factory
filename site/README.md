# Static showcase

Serve the committed tree directly; no build or runtime dependencies:

```sh
python3 -m http.server 4317 --bind 127.0.0.1 --directory site
```

The HTML, CSS, JavaScript, SVG and four unmodified OFL font faces are local.
There is no analytics, worker, remote runtime asset or network API client.
External anchors are explicitly labeled declared source targets; their public
availability is pending verification. An existing trusted checkout supplies the
recommended setup route. Pages publication is a separate owner action through
manual workflow dispatch; this tree does not establish a deployment.

## Canonical setup prompt

`docs/copy-prompt.txt` is the prompt template. `site/hosts.json` is the single
reviewed host map (installer host argument and invocation prefix). From the
repository root:

```sh
python3 site/scripts/sync_prompt.py
python3 site/scripts/sync_prompt.py --check
```

The explicit sync updates only the marked README setup-prompt blocks,
`site/scripts/setup-data.js` and the served `site/setup-prompt.txt` template.
The read-only check exits nonzero on drift. The served page uses committed data;
no build or fetch is required. Clipboard denial opens and selects the complete
prompt for manual copying and reports failure through the polite status region.
The source test compares every complete host string, including line breaks.
A DOM value inspection is not actual clipboard readback proof.

## Review

```sh
python3 -m unittest discover -s tests -p test_showcase.py -v
bash scripts/check_all.sh
```

Static tests cover local references, canonical prompt drift, font hashes and
complete licenses, structural accessibility, content contracts, reduced-motion
hooks, source budgets and the manual SHA-pinned Pages workflow. Negative fixtures
exercise broken anchors, remote resources, unsafe links, duplicate IDs, missing
alt text and escaping paths. An optional developer Node.js unit fixture executes the actual page script with
controlled clipboard promises to check overlapping attempts and host changes.
Missing Node reports an unverified skip; it is not a shipped runtime dependency.
This synthetic unit proof does not establish browser clipboard effects.

Static checks do not prove browser rendering,
clipboard effects, live host integration, publication or WCAG conformance.

Browser review uses the supported computer-use API on the loopback page. Inspect
360×640, 768×1024 and 1440×900; keyboard tabs (arrows, Home/End), Enter activation,
copy success/denial, native disclosures, internal anchors, focus and 200% reflow.
Observe actual loaded fonts, all requests, console errors and reduced-motion
parity. Keep screenshots outside run JSON/text directories; identify the exact
source commit, engine, viewport and settings in the review receipt.

Design budgets: 30 KiB gzip CSS, 10 KiB gzip JavaScript, 750 KiB first-view local
resources including fonts. The static suite bounds source bytes conservatively;
it does not establish measured transfer, LCP, CLS, interaction latency or field
Core Web Vitals. No runtime telemetry is collected. The three below-fold marketing
cards in `site/img/` have fixed intrinsic dimensions and lazy loading. They are
byte-identical exports of the root marketing masters; the site needs no build.
See the [launch asset runbook](../docs/launch-assets.md) for their finite inventory,
explicit developer prerequisites, regeneration, visual review and manual upload.

## Publication source references

The manual workflow follows the official GitHub Pages custom workflow contract:
[GitHub Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
Action tag identities were resolved through the official `actions/*` GitHub API
on 2026-10-15. Complete pinned commit IDs are in `.github/workflows/pages.yml`.
The workflow uploads only `site/`; it does not enable Pages or publish on push.
Font source revisions, byte counts, hashes and notices are in
[font sources](fonts/SOURCES.md).
