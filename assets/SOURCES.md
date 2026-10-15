# Marketing asset sources

The seven HTML templates, shared SVG system diagrams and their PNG renderings
are original Software Factory artwork, distributed under the project's MIT
license. The project mark is the original `site/img/mark.svg`. Host names are
plain text; no vendor logo or endorsement is used. Product names belong to their
respective owners; see [the non-affiliation notice](../NOTICE.md).

Templates directly reuse `site/styles/tokens.css` and `site/styles/base.css`.
The latter declares the four local, unmodified OFL font faces. Exact upstream
revisions, download URLs, SHA-256 hashes, byte lengths and full family notices
are recorded in [font sources](../site/fonts/SOURCES.md) and its sibling manifest:

- Bricolage Grotesque 96pt Bold, normal 700, project heading face.
- Inter Regular and SemiBold, normal 400 and 600, reading copy.
- JetBrains Mono Regular, normal 400, compact labels.

The renderer checks those source hashes and actual named font loading. Raster
renderings do not replace the notices accompanying the redistributed font files.
No font was modified, converted, subset, installed globally or fetched at render
time. These HTML templates use local CSS, fonts, scripts and images only.

`manifest.json` is the finite output/input inventory. `toolchain.json` pins the
optional development toolchain. `render-receipt.json` records each actual render's
input/output hashes and observed readiness, browser and launch configuration.
It is build evidence, not proof of release publication, deployment or endorsement.

## Developer tool sources

- [Playwright Python 1.64.0 release](https://github.com/microsoft/playwright-python/releases/tag/v1.64.0)
- [Official package metadata](https://pypi.org/project/playwright/1.64.0/)
- [Browser launch API](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch)
- [Browser management](https://playwright.dev/python/docs/browsers)

The official package resolves Chromium headless shell revision 1248, version
156.0.8078.4. `assets/tools/capture.py` uses the optional developer API with
`chromium_sandbox=True`. The default unsafe SwiftShader opt-in is removed because
these templates use no WebGL. Actual launch arguments are inspected for sandbox
bypasses. The helper and its dependency are excluded from consumer release
payloads; `scripts/render_assets.py` itself imports only the standard library.

The lifecycle illustration has one canonical editable source at
`site/img/delivery-graph.svg`. Its overview (`factory-cycle`, 1000 × 600,
26 labels) is shared by five marketing compositions and the showcase hero.
Its expanded map (`factory-system`, 1440 × 1080, 52 labels, translated 660
units down the source canvas) is shared by the showcase lifecycle section;
the `system-map` view fragment opens that map directly. The site's prose guide
provides a readable equivalent at narrow widths.

Both views explain relationships in the canonical feature and bug workflows:
ongoing orchestration, dependency readiness, parallel stories, independent proof,
repair, sequential integration, approved delivery, authorized feedback and
conditional human decisions. The expanded view includes separating experiments,
independently reviewed no-fix closure, recovery and reviewed improvements.
They assert no live activity or always-on monitoring. Text and geometry are
original to this pack. Actual PNG capture records exact cloned text identities,
finite in-frame SVG geometry, label bounds inside the SVG frame, label
bounding-box separation and custom Inter glyphs. These checks do not establish
visibility through clip paths or occluding elements, connector clearance or
containment inside each card. Actual pixel inspection establishes those
relationships and the site's expanded presentation. The standalone SVG links
the same-origin base stylesheet through XML stylesheet metadata; its actual
font use is inspected separately from cloned HTML glyphs.
