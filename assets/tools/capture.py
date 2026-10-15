"""Optional pinned developer tool. Excluded from all consumer release payloads."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import signal
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PACKAGES = {"playwright": "1.64.0", "greenlet": "3.5.6", "pyee": "14.0.0", "typing_extensions": "4.16.0"}
SIZES = {"social-preview": (1280, 640), "hero": (1600, 900), "loop": (1200, 800),
         "team": (1200, 800), "hosts": (1200, 800), "launch-landscape": (1200, 675),
         "launch-portrait": (1080, 1350)}
CYCLE_ASSETS = {"social-preview", "hero", "loop", "launch-landscape", "launch-portrait"}


def walk_nodes(node):
    yield node
    for key in ("children", "shadowRoots"):
        for child in node.get(key, []):
            yield from walk_nodes(child)


SVG_VIEWS = {"factory-cycle": ([0, 0, 1000, 600], 26),
             "factory-system": ([0, 660, 1440, 1080], 52)}


def cycle_evidence(page):
    return svg_evidence(page)


def svg_evidence(page, selector="svg.factory-cycle", fragment="factory-cycle",
                 reference="../../site/img/delivery-graph.svg#factory-cycle"):
    """Inspect the actual clone: exact view, source text, geometry and custom glyphs."""
    if fragment not in SVG_VIEWS or reference.rsplit("#", 1)[-1] != fragment:
        raise ValueError("unexpected shared SVG variant")
    viewbox, count = SVG_VIEWS[fragment]
    observed = page.locator(selector).evaluate("element => { const b = element.getBoundingClientRect(); return {viewbox: [element.viewBox.baseVal.x, element.viewBox.baseVal.y, element.viewBox.baseVal.width, element.viewBox.baseVal.height], bounds: [b.left,b.top,b.right,b.bottom]}; }")
    geometry = page.locator(selector + " use").evaluate(
        "element => { const b = element.getBBox(); return [b.x, b.y, b.width, b.height]; }")
    if (observed.get("viewbox") != viewbox or len(geometry) != 4
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in geometry)
            or geometry[2] < viewbox[2] * .9 or geometry[3] < viewbox[3] * .9
            or geometry[0] < viewbox[0] or geometry[1] < viewbox[1]
            or geometry[0] + geometry[2] > viewbox[0] + viewbox[2]
            or geometry[1] + geometry[3] > viewbox[1] + viewbox[3]):
        raise ValueError("shared SVG did not resolve its reviewed view and geometry")
    response = page.request.get(page.url.split("/assets/", 1)[0] + "/site/img/delivery-graph.svg")
    data = response.body()
    if response.status != 200 or len(data) > 100000:
        raise ValueError("missing shared SVG source")
    root = ET.fromstring(data)
    group = next(node for node in root.iter() if node.get("id") == fragment)
    expected = ["".join(node.itertext()) for node in group.iter("{http://www.w3.org/2000/svg}text")]
    if len(expected) != count:
        raise ValueError("unexpected shared SVG source text count")
    client = page.context.new_cdp_session(page)
    try:
        client.send("DOM.enable")
        client.send("CSS.enable")
        document = client.send("DOM.getDocument", {"depth": -1, "pierce": True})
        uses = [node for node in walk_nodes(document["root"]) if node.get("localName") == "use"]
        selected = [node for node in uses if node.get("attributes") == ["href", reference]]
        if len(selected) != 1 or (selector == "svg.factory-cycle" and len(uses) != 1):
            raise ValueError("unexpected shared SVG reference")
        texts = [node for node in walk_nodes(selected[0]) if node.get("localName") == "text"]
        if len(texts) != count:
            raise ValueError("shared SVG text did not resolve")
        observations = []
        for node, label in zip(texts, expected, strict=True):
            actual = "".join(child.get("nodeValue", "") for child in node.get("children", []))
            if not actual or actual != label:
                raise ValueError("shared SVG text differs from its source")
            fonts = client.send("CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]})["fonts"]
            if not fonts or any(not font["isCustomFont"] or font["glyphCount"] <= 0
                                or font["postScriptName"] not in {"Inter-Regular", "Inter-SemiBold"}
                                for font in fonts):
                raise ValueError("shared SVG used a missing or fallback font")
            object_id = client.send("DOM.resolveNode", {"nodeId": node["nodeId"]})["object"]["objectId"]
            bounds = client.send("Runtime.callFunctionOn", {"objectId": object_id,
                "functionDeclaration": "function() {const b=this.getBoundingClientRect(); return [b.left,b.top,b.right,b.bottom];}",
                "returnByValue": True})["result"]["value"]
            client.send("Runtime.releaseObject", {"objectId": object_id})
            limit = observed["bounds"]
            if (len(bounds) != 4 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds)
                    or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]
                    or bounds[0] < limit[0] - .5 or bounds[1] < limit[1] - .5
                    or bounds[2] > limit[2] + .5 or bounds[3] > limit[3] + .5):
                raise ValueError("shared SVG text is unresolved or clipped")
            for previous in observations:
                other = previous["bounds"]
                if min(bounds[2], other[2]) - max(bounds[0], other[0]) > .5 and min(bounds[3], other[3]) - max(bounds[1], other[1]) > .5:
                    raise ValueError("shared SVG labels overlap: " + previous["text"] + " / " + actual)
            observations.append({"text": actual, "fonts": fonts, "bounds": bounds})
        return {"reference": reference, "viewbox": viewbox, "geometry": geometry,
                "bounds": observed["bounds"], "text_fonts": observations}
    finally:
        client.detach()


def read_job(path):
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > 32000:
        raise ValueError("invalid private capture job")
    parent = path.parent
    if parent.is_symlink() or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
        raise ValueError("capture job requires an owned private temporary directory")
    job = json.loads(path.read_text())
    if set(job) != {"version", "origin", "assets"} or job["version"] != 1:
        raise ValueError("invalid capture job schema")
    origin = urlsplit(job["origin"])
    if origin.scheme != "http" or origin.hostname != "127.0.0.1" or not origin.port or origin.path or origin.query or origin.fragment or origin.username:
        raise ValueError("capture requires the staged loopback origin")
    if len(job["assets"]) != 7 or {entry["id"] for entry in job["assets"]} != set(SIZES):
        raise ValueError("capture requires all seven known assets")
    for entry in job["assets"]:
        if (entry["width"], entry["height"]) != SIZES[entry["id"]] or entry["template"] != f'assets/templates/{entry["id"]}.html':
            raise ValueError("capture template or viewport is not reviewed")
    return job


def capture_page(browser, origin, entry, stage):
    context = browser.new_context(
        viewport={"width": entry["width"], "height": entry["height"]},
        device_scale_factor=1, locale="en-US", timezone_id="UTC", color_scheme="light",
        reduced_motion="reduce", service_workers="block", accept_downloads=False,
        permissions=[],
    )
    errors, requests = [], []

    def route_request(route):
        url = urlsplit(route.request.url)
        if f"{url.scheme}://{url.netloc}" != origin or url.username or url.fragment:
            errors.append("blocked nonlocal resource")
            route.abort()
        else:
            route.continue_()

    context.route("**/*", route_request)
    context.on("request", lambda request: requests.append({"path": urlsplit(request.url).path,
                                                            "type": request.resource_type}))
    context.on("requestfailed", lambda request: errors.append("resource failed: " + urlsplit(request.url).path))
    context.on("response", lambda response: errors.append("resource status: " + str(response.status)) if response.status != 200 else None)
    page = None
    try:
        page = context.new_page()
        page.on("pageerror", lambda _error: errors.append("page exception"))
        page.on("console", lambda message: errors.append("console " + message.type) if message.type in ("error", "warning") else None)
        page.goto(origin + "/" + entry["template"], wait_until="load", timeout=30000)
        page.wait_for_selector('html[data-render-ready]', state="attached", timeout=30000)
        ready = page.evaluate("window.SF_RENDER_REPORT")
        if not isinstance(ready, dict) or ready.get("failed") or ready.get("overflow") or errors:
            raise ValueError("template readiness or resource checks failed")
        cycle = cycle_evidence(page) if entry["id"] in CYCLE_ASSETS else None
        page.screenshot(path=str(stage / (entry["id"] + ".png")), type="png", full_page=False,
                        animations="disabled", caret="hide", timeout=30000)
        ready = page.evaluate("window.SF_RENDER_REPORT")
        if errors or ready.get("failed") or ready.get("overflow"):
            raise ValueError("resource or readiness error during screenshot")
        return {"id": entry["id"], "ready": ready, "cycle": cycle, "errors": errors, "requests": requests}
    except Exception:
        diagnostic = {"id": entry["id"], "errors": errors[:32], "requests": requests[:64]}
        if page is not None:
            try:
                diagnostic["ready"] = page.evaluate("window.SF_RENDER_REPORT")
            except PlaywrightError:
                diagnostic["ready"] = "unavailable"
        # stderr is retained only in the caller's private evidence directory.
        print("capture failure: " + json.dumps(diagnostic)[:16000], file=sys.stderr, flush=True)
        raise
    finally:
        context.close()


def capture(job_path):
    job = read_job(job_path)
    packages = {name: importlib.metadata.version(name) for name in PACKAGES}
    if packages != PACKAGES:
        raise ValueError("developer dependency versions differ from reviewed pins")
    stage = job_path.parent
    report = {"packages": packages, "python": platform.python_version(), "system": platform.system(),
              "settings": {"sandbox": True, "scale": 1, "locale": "en-US", "timezone": "UTC",
                           "color_scheme": "light", "service_workers": "block", "permissions": []},
              "captures": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, chromium_sandbox=True, timeout=30000,
            downloads_path=str(stage / "downloads"),
            ignore_default_args=["--enable-unsafe-swiftshader"],
        )
        try:
            report["browser_version"] = browser.version
            if browser.version != "156.0.8078.4":
                raise ValueError("observed Chromium version differs from reviewed pin")
            for entry in job["assets"]:
                report["captures"].append(capture_page(browser, job["origin"], entry, stage))
        finally:
            browser.close()
    (stage / "browser-report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(_signum, _frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise RuntimeError("developer capture interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        capture(args.job)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print("asset capture complete")


if __name__ == "__main__":
    main()
