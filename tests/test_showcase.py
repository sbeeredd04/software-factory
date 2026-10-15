"""Static showcase contracts; browser evidence is collected separately."""
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def audit_html(source, site):
    """Reject broken local resources, inaccessible images and ambiguous anchors."""
    tags = Page(source).tags
    ids = [a["id"] for _, a in tags if "id" in a]
    errors = []
    if len(ids) != len(set(ids)):
        errors.append("duplicate id")
    for tag, attrs in tags:
        if tag == "img" and "alt" not in attrs:
            errors.append("image missing alt")
        for field in ("src", "href"):
            value = attrs.get(field, "")
            if not value:
                continue
            if value.startswith("#"):
                if value[1:] not in ids:
                    errors.append("missing anchor")
                continue
            parsed = urlsplit(value)
            resource = tag != "a"
            if parsed.scheme or parsed.netloc:
                if resource:
                    errors.append("remote resource")
                elif parsed.scheme != "https":
                    errors.append("unsafe navigation")
            elif resource or tag == "a":
                path = (site / parsed.path).resolve()
                if not path.is_relative_to(site.resolve()) or not path.is_file():
                    errors.append("missing or escaping local resource")
                elif tag == "use":
                    try:
                        targets = {node.get("id") for node in ET.fromstring(path.read_text()).iter()}
                        if not parsed.fragment or parsed.fragment not in targets:
                            errors.append("missing SVG fragment")
                    except ET.ParseError:
                        errors.append("invalid SVG resource")
    return errors


def root_motion_rules(css):
    """Read declarations from a rule that targets the document root itself."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    result = {}
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if "html[data-motion='off']" not in [part.strip() for part in selectors.split(",")]:
            continue
        for declaration in declarations.split(";"):
            if ":" in declaration:
                key, value = declaration.split(":", 1)
                result[key.strip()] = value.strip()
    return result


class ShowcaseTests(unittest.TestCase):
    def source(self):
        return (SITE / "index.html").read_text()

    def test_static_tree_and_resources(self):
        for name in ("styles", "scripts", "img", "fonts"):
            self.assertTrue((SITE / name).is_dir(), name)
        self.assertEqual(audit_html(self.source(), SITE), [])
        self.assertFalse((SITE / "package.json").exists())

    def test_shared_cycle_and_risk_adaptive_factory_copy(self):
        source = self.source()
        self.assertEqual(source.count('href="img/delivery-graph.svg#factory-cycle"'), 1)
        for phrase in ("Your whole", "continuously shipped improvements", "BMad epics", "agreed autonomy",
                       "Reserved", "proof gates", "active coding host", "resume the affected step"):
            self.assertIn(phrase.lower(), source.lower())
        for stale in ("Each epic has a real acceptance checkpoint", "Human epic acceptance", "Human epic checkpoint"):
            self.assertNotIn(stale, source)
        self.assertIn("missing SVG fragment", audit_html(
            source.replace('href="img/delivery-graph.svg#factory-cycle"', 'href="img/delivery-graph.svg#absent-cycle"'), SITE))

    def test_substantive_sections_and_palette(self):
        page = Page(self.source())
        ids = {a.get("id") for _, a in page.tags}
        self.assertTrue({"loop", "bugs", "evidence", "setup", "skills", "team", "hosts", "responsibilities", "faq"} <= ids)
        for path in (ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn(f"/skills/{path.parent.name}/SKILL.md", self.source())
        for path in (ROOT / "agents").glob("sf-*.md"):
            self.assertIn(f"/agents/{path.name}", self.source())

    def test_semantic_structure(self):
        tags = Page(self.source()).tags
        self.assertEqual(sum(t == "h1" for t, _ in tags), 1)
        self.assertEqual(sum(t == "main" for t, _ in tags), 1)
        self.assertIn(("html", {"lang": "en"}), tags)
        self.assertIn('href="#main"', self.source())
        self.assertIn('role="status"', self.source())
        self.assertIn('<caption>', self.source())
        previous = 1
        for tag, _ in tags:
            if re.fullmatch(r"h[1-6]", tag):
                level = int(tag[1])
                self.assertLessEqual(level, previous + 1)
                previous = level

    def test_canonical_prompt_derivations_are_current(self):
        result = subprocess.run([sys.executable, str(SITE / "scripts/sync_prompt.py"), "--check"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        template = (ROOT / "docs/copy-prompt.txt").read_text()
        hosts = json.loads((SITE / "hosts.json").read_text())
        data = (SITE / "scripts/setup-data.js").read_text()
        payload = json.loads(data.removeprefix("window.SF_SETUP = ").rstrip(";\n"))
        self.assertEqual(set(payload), set(hosts))
        index = (SITE / "index.html").read_text()
        fallback = re.search(r'<code id="install-command">([^<]+)</code>', index)
        route = re.search(r'<h3>Full project setup.*?</h3>.*?<pre>([^<]+)</pre>', index, re.DOTALL)
        self.assertIsNotNone(fallback)
        self.assertIsNotNone(route)
        self.assertEqual(payload["claude-code"]["command"], unescape(fallback.group(1)))
        self.assertEqual(payload["claude-code"]["command"], unescape(route.group(1)))
        for key, host in hosts.items():
            expected = template.format(**host)
            self.assertEqual(payload[key]["prompt"], expected)
            self.assertIn(expected.rstrip(), (ROOT / "README.md").read_text())
            self.assertEqual(payload[key]["command"], f'python3 -I -B install.py install --host {host["host"]} --skip-bmad --project "<this-project>" --profile full --dry-run')
            self.assertIn(payload[key]["command"], payload[key]["prompt"])

    def test_font_hashes_licenses_and_local_css(self):
        manifest = json.loads((SITE / "fonts/manifest.json").read_text())
        self.assertEqual(len(manifest), 4)
        for face in manifest:
            binary = SITE / "fonts" / face["file"]
            self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), face["sha256"])
            self.assertTrue(binary.read_bytes().startswith(b"wOF2"))
            license_text = (SITE / "fonts" / face["license"]).read_text()
            self.assertIn("SIL OPEN FONT LICENSE Version 1.1", license_text)
            self.assertIn(face["sha256"], (SITE / "fonts/SOURCES.md").read_text())
        css = "\n".join(p.read_text() for p in (SITE / "styles").glob("*.css"))
        self.assertEqual(css.count("font-display: swap"), 4)
        self.assertNotRegex(css, r"https?://|@import")
        for value in re.findall(r'url\([\"\']?([^\)\"\']+)', css):
            self.assertTrue((SITE / "styles" / value).is_file(), value)

    def test_motion_focus_and_small_screen_hooks(self):
        css = "\n".join(p.read_text() for p in (SITE / "styles").glob("*.css"))
        for hook in ("prefers-reduced-motion", ":focus-visible", "@media", "overflow-wrap", "min-width: 0"):
            self.assertIn(hook, css)
        self.assertIn('name="viewport"', self.source())
        self.assertIn('aria-pressed="false"', self.source())

    def test_copy_failure_and_tabs_contract(self):
        js = (SITE / "scripts/main.js").read_text()
        for hook in ("clipboard.writeText", "catch", "ArrowRight", "ArrowLeft", "Home", "End", "aria-selected", "readOnly", "textContent", "select()"):
            self.assertIn(hook, js)
        self.assertNotIn("innerHTML", js)
        self.assertIn("Copy unavailable", js)
        failure = js.split("} catch {", 1)[1].split("  });", 1)[0]
        self.assertIn("copy.textContent = 'Copy setup prompt';", failure)

    def prompt_fixture(self, parent):
        for relative in ("docs/copy-prompt.txt", "site/hosts.json", "site/scripts/sync_prompt.py"):
            target = parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        (parent / "README.md").write_text("Before\n<!-- setup-prompts:start -->\nold\n<!-- setup-prompts:end -->\nAfter\n")
        script = parent / "site/scripts/sync_prompt.py"
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return script

    def test_prompt_generator_refuses_ambiguous_markers_without_writes(self):
        start, end = "<!-- setup-prompts:start -->", "<!-- setup-prompts:end -->"
        for broken in ("Replacement overview.\n", start, end, start + start + end, end + start):
            with self.subTest(readme=broken), tempfile.TemporaryDirectory(prefix="sf-showcase-prompt-") as temp:
                parent = Path(temp)
                script = self.prompt_fixture(parent)
                (parent / "README.md").write_text(broken)
                before = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
                for args in (["--check"], []):
                    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, check=False)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    after = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
                    self.assertEqual(after, before)

    def test_prompt_sync_preserves_unowned_readme_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="sf-showcase-prompt-") as temp:
            parent = Path(temp)
            script = self.prompt_fixture(parent)
            readme = (parent / "README.md").read_text()
            self.assertTrue(readme.startswith("Before\n<!-- setup-prompts:start -->"))
            self.assertTrue(readme.endswith("<!-- setup-prompts:end -->\nAfter\n"))
            before = {str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
            result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({str(p.relative_to(parent)): p.read_bytes() for p in parent.rglob("*") if p.is_file()}, before)

    def test_manual_motion_off_stops_root_scroll_and_transitions(self):
        css = (SITE / "styles/sections.css").read_text()
        rules = root_motion_rules(css)
        self.assertEqual(rules.get("scroll-behavior"), "auto !important")
        self.assertEqual(rules.get("animation"), "none !important")
        self.assertEqual(rules.get("transition"), "none !important")
        bad = (ROOT / "tests/fixtures/showcase/descendants-only-motion.css").read_text()
        self.assertEqual(root_motion_rules(bad), {})

    @unittest.skipUnless(shutil.which("node"), "developer Node.js unavailable; copy overlap remains unverified")
    def test_copy_overlap_keeps_latest_attempt_and_host_state(self):
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "tests/fixtures/showcase/copy-overlap.cjs"), str(SITE / "scripts/main.js")],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("copy overlap: 3 cases, 0 failed", result.stdout)

    def test_first_view_source_budget(self):
        files = [p for p in SITE.rglob("*") if p.suffix in {".html", ".css", ".js", ".svg", ".woff2"}]
        total = sum(p.stat().st_size for p in files)
        self.assertLess(total, 750 * 1024)
        for folder, cap in (("styles", 30), ("scripts", 10)):
            size = sum(len(gzip.compress(p.read_bytes(), mtime=0)) for p in (SITE / folder).glob("*.*") if p.suffix in {".css", ".js"})
            self.assertLess(size, cap * 1024)

    def test_manual_pages_workflow(self):
        source = (ROOT / ".github/workflows/pages.yml").read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertNotRegex(source, r"(?m)^  (push|pull_request|schedule):")
        self.assertIn("path: site/", source)
        self.assertIn("needs: build", source)
        self.assertIn("name: github-pages", source)
        self.assertIn("pages: write", source)
        self.assertIn("pages: read", source)
        for action in re.findall(r"uses: (\S+)", source):
            self.assertRegex(action, r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_negative_resource_and_semantics_fixtures(self):
        fixtures = ROOT / "tests/fixtures/showcase"
        expectations = json.loads((fixtures / "expected.json").read_text())
        for name, expected in expectations.items():
            with self.subTest(name=name):
                self.assertIn(expected, audit_html((fixtures / name).read_text(), SITE))

    def test_honest_boundaries_and_original_diagram(self):
        source = self.source()
        for phrase in ("Illustrative workflow", "Synthetic specimen", "Pre-release", "skills-only", "native Windows", "independent", "checkpoint", "BMad Method v6", "session"):
            self.assertIn(phrase, source)
        svg = (SITE / "img/delivery-graph.svg").read_text()
        self.assertIn("<title", svg)
        self.assertIn("<desc", svg)
        self.assertNotIn("http", svg.replace('xmlns="http://www.w3.org/2000/svg"', ""))


if __name__ == "__main__":
    unittest.main()
