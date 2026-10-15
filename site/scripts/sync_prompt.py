"""Synchronize committed, buildless prompt views; --check never writes."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START = "<!-- setup-prompts:start -->"
END = "<!-- setup-prompts:end -->"


def derived_files():
    template = (ROOT / "docs/copy-prompt.txt").read_text()
    hosts = json.loads((ROOT / "site/hosts.json").read_text())
    payload = {}
    blocks = [START, "", "### Copy a setup prompt", "", "Use a trusted local pack checkout. Replace `<this-project>` with the intended project path.", "The complete prompts below match the showcase's host selector.", ""]
    for key, host in hosts.items():
        prompt = template.format(**host)
        payload[key] = {"label": host["label"], "invocation": host["invocation"], "command": f'python3 install.py install --host {host["host"]} --skip-bmad --project <this-project> --dry-run', "prompt": prompt}
        blocks += [f'#### {host["label"]}', "", "```text", prompt.rstrip(), "```", ""]
    blocks += [END]
    readme = (ROOT / "README.md").read_text()
    if START in readme and END in readme:
        before, remaining = readme.split(START, 1)
        _, after = remaining.split(END, 1)
        readme = before + "\n".join(blocks) + after
    else:
        readme = readme.replace("\n## Community", "\n" + "\n".join(blocks) + "\n\n## Community")
    return {
        ROOT / "site/scripts/setup-data.js": "window.SF_SETUP = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        ROOT / "README.md": readme,
        ROOT / "site/setup-prompt.txt": template,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = []
    for path, expected in derived_files().items():
        if path.exists() and path.read_text() == expected:
            continue
        drift.append(str(path.relative_to(ROOT)))
        if not args.check:
            path.write_text(expected)
    if args.check and drift:
        print("Prompt drift: " + ", ".join(drift), file=sys.stderr)
        return 1
    print("Prompt views are current." if args.check else "Prompt views synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
