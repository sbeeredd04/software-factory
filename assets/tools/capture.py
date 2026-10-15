"""Optional pinned developer tool. Excluded from all consumer release payloads."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

PACKAGES = {"playwright": "1.64.0", "greenlet": "3.5.6", "pyee": "14.0.0", "typing_extensions": "4.16.0"}
SIZES = {"social-preview": (1280, 640), "hero": (1600, 900), "loop": (1200, 800),
         "team": (1200, 800), "hosts": (1200, 800), "launch-landscape": (1200, 675),
         "launch-portrait": (1080, 1350)}


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
    try:
        page = context.new_page()
        page.on("pageerror", lambda _error: errors.append("page exception"))
        page.on("console", lambda message: errors.append("console " + message.type) if message.type in ("error", "warning") else None)
        page.goto(origin + "/" + entry["template"], wait_until="load", timeout=30000)
        page.wait_for_selector('html[data-render-ready="true"]', state="attached", timeout=30000)
        ready = page.evaluate("window.SF_RENDER_REPORT")
        if not isinstance(ready, dict) or ready.get("failed") or ready.get("overflow") or errors:
            raise ValueError("template readiness or resource checks failed")
        page.screenshot(path=str(stage / (entry["id"] + ".png")), type="png", full_page=False,
                        animations="disabled", caret="hide", timeout=30000)
        ready = page.evaluate("window.SF_RENDER_REPORT")
        if errors or ready.get("failed") or ready.get("overflow"):
            raise ValueError("resource or readiness error during screenshot")
        return {"id": entry["id"], "ready": ready, "errors": errors, "requests": requests}
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
    capture(args.job)
    print("asset capture complete")


if __name__ == "__main__":
    main()
