"""Literal README adoption contract, exercised without host agent CLIs."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import support

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PYTHON = shutil.which("python3.12") or sys.executable
DIAGRAMS = ("hero-loop", "feature-loop", "bug-loop", "install-flow",
            "host-projection", "onboarding", "evolve-loop", "eval-flow", "board-roadmap")


def literal_argv(document: str, host: str, pack: Path, project: Path) -> list[str]:
    """Recognize exactly the documented local preview grammar, never a shell script."""
    if host not in ("claude-code", "cursor", "codex"):
        raise ValueError("unsupported host")
    lines = [line for line in document.splitlines()
             if line.startswith('"$SF_PYTHON" -I -B "$SF_PACK/install.py" install ')]
    if len(lines) != 1:
        raise ValueError("README needs one literal preview command")
    tokens = shlex.split(lines[0])
    expected = ["$SF_PYTHON", "-I", "-B", "$SF_PACK/install.py", "install",
                "--host", "$SF_HOST", "--project", "$SF_PROJECT", "--profile", "full",
                "--skip-bmad", "--dry-run"]
    if tokens != expected or "<" in lines[0] or ">" in lines[0]:
        raise ValueError("README install command drift")
    return [str(PYTHON), "-I", "-B", str(pack / "install.py"), "install",
            "--host", host, "--project", str(project), "--profile", "full",
            "--skip-bmad", "--dry-run"]


def diagram_contract(document: str) -> None:
    bodies = re.findall(r"^```mermaid\n(.*?)\n```$", document, re.MULTILINE | re.DOTALL)
    if len(bodies) != len(DIAGRAMS):
        raise ValueError("nine diagram bodies required")
    for name, body in zip(DIAGRAMS, bodies):
        anchor = "board-and-roadmap" if name == "board-roadmap" else name
        if body != (ROOT / "docs/diagrams" / f"{name}.mmd").read_text().rstrip("\n"):
            raise ValueError(f"{name} body changed")
        for link in (f"docs/diagrams/{name}.svg", f"docs/diagrams/README.md#{anchor}"):
            if link not in document:
                raise ValueError(f"{name} alternative missing")


def controlled_doctor_log(contents: str, gh: Path) -> None:
    """The one permitted provider probe is exactly gh auth status."""
    if contents.splitlines() != [f"{gh} auth status"]:
        raise ValueError("unexpected provider or host command")


def release_link_errors(document: str, files: dict[str, bytes]) -> list[str]:
    """Check README links and standalone images against actual archive members."""
    references = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", document)
    references += re.findall(r"\[(?:!\[[^\]]*\]\([^)]*\)|[^\]]*)\]\(([^)]+)\)", document)
    errors = []
    for reference in references:
        if "://" in reference or reference.startswith("mailto:"):
            continue
        target, _, anchor = reference.partition("#")
        path = posixpath.normpath(target or "README.md")
        if path not in files:
            errors.append(f"released README links to absent {reference}")
            continue
        if anchor:
            headings = re.findall(r"^#{1,6}\s+(.+?)\s*#*$", files[path].decode("utf-8"), re.MULTILINE)
            slugs = {re.sub(r"[^\w -]", "", heading.replace("`", "").lower()).replace(" ", "-")
                     for heading in headings}
            if anchor not in slugs:
                errors.append(f"released README links to absent anchor {reference}")
    return errors


class ReadmeJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sf-readme-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.env, self.records, self.guard = support.recorder_env()
        self.stubs = self.guard.parent
        self.addCleanup(shutil.rmtree, self.records, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.stubs, ignore_errors=True)
        self.home, self.home_snapshot = support.home_sentinel(self.base)
        self.env["HOME"] = str(self.home)
        self.env["CODEX_HOME"] = str(self.home / ".codex")
        self.home_before = self.home_snapshot()
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        for name in ("claude-code", "agent", "droid", "gh"):
            stub = self.stubs / name
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$SF_GUARD_LOG"\nexit 127\n')
            stub.chmod(0o755)

    def tearDown(self):
        self.assertFalse(self.guard.exists(), "forbidden host/provider CLI invoked")
        self.assertEqual([], list(self.records.iterdir()), "package/download tool invoked")
        self.assertEqual(self.home_before, self.home_snapshot(), "isolated global settings changed")

    def run_cli(self, *args, cwd=None):
        return subprocess.run([str(arg) for arg in args], cwd=cwd or ROOT, env=self.env,
                              capture_output=True, text=True, timeout=90, check=False)

    def consumer(self, name):
        project = self.base / name
        shutil.copytree(ROOT / "examples/minimal", project)
        git = self.run_cli("git", "init", project)
        self.assertEqual(0, git.returncode, git.stderr)
        (project / "user-settings.json").write_bytes(b'{"owner":"keep"}\n')
        return project

    def test_literal_command_refuses_drift(self):
        readme = README.read_text()
        project = self.base / "project"
        self.assertEqual("--dry-run", literal_argv(readme, "codex", ROOT, project)[-1])
        for changed in (readme.replace("--skip-bmad --dry-run", "--dry-run", 1),
                        readme.replace("--profile full", "--profile skills-only", 1),
                        readme.replace("--host \"$SF_HOST\"", "--host <host>", 1)):
            with self.assertRaises(ValueError):
                literal_argv(changed, "codex", ROOT, project)
        with self.assertRaises(ValueError):
            literal_argv(readme, "unknown", ROOT, project)

    def test_readme_directory_selection_stops_on_failed_cd(self):
        readme = README.read_text()
        block = readme.split("## Install locally\n", 1)[1].split("```sh\n", 1)[1].split("\n```", 1)[0]
        self.assertIn("cd '/absolute/path/to/consumer-project' || exit 1", block)
        self.assertIn("cd '/absolute/path/to/trusted/software-factory' || exit 1", block)
        project = self.consumer("consumer with spaces")
        pack = self.base / "trusted pack with spaces"
        pack.mkdir()
        recorder = self.base / "python-argv.txt"
        stub = self.stubs / "python3"
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SF_INSTALL_LOG"\n')
        stub.chmod(0o755)
        env = dict(self.env, SF_INSTALL_LOG=str(recorder))
        for bad_project, bad_pack in ((self.base / "missing consumer", pack),
                                      (project, self.base / "missing pack")):
            script = block.replace("'/absolute/path/to/consumer-project'", shlex.quote(str(bad_project)))
            script = script.replace("'/absolute/path/to/trusted/software-factory'", shlex.quote(str(bad_pack)))
            failed = subprocess.run(["/bin/sh", "-c", script], cwd=ROOT, env=env,
                                    capture_output=True, text=True, check=False)
            self.assertNotEqual(0, failed.returncode)
            self.assertFalse(recorder.exists(), "installer ran after failed directory selection")
        script = block.replace("'/absolute/path/to/consumer-project'", shlex.quote(str(project)))
        script = script.replace("'/absolute/path/to/trusted/software-factory'", shlex.quote(str(pack)))
        selected = subprocess.run(["/bin/sh", "-c", script], cwd=ROOT, env=env,
                                  capture_output=True, text=True, check=False)
        self.assertEqual(0, selected.returncode, selected.stderr)
        self.assertIn(str(project), recorder.read_text().splitlines())
        self.assertIn(str(pack / "install.py"), recorder.read_text().splitlines())
        self.assertIn('cd "$SF_PROJECT" || exit 1', readme.replace(r"\|", "|"))
        self.assertIn('skills@1.7.2 add "$SF_PACK/skills"', readme)

    def test_nine_canonical_diagrams_and_alternatives(self):
        readme = README.read_text()
        diagram_contract(readme)
        with self.assertRaises(ValueError):
            diagram_contract(readme.replace("docs/diagrams/hero-loop.svg", "docs/diagrams/absent.svg", 1))
        first = (ROOT / "docs/diagrams/hero-loop.mmd").read_text().rstrip("\n")
        second = (ROOT / "docs/diagrams/feature-loop.mmd").read_text().rstrip("\n")
        with self.assertRaises(ValueError):
            diagram_contract(readme.replace(first, second, 1))

    def test_first_screen_and_prompt_parity(self):
        readme = README.read_text()
        lines = readme.splitlines()
        self.assertLess(lines.index("## Quickstart"), 130)
        for term in ("pre-release", "BMad", "risk", "MIT", "CI", "non-affiliated"):
            self.assertIn(term, readme)
        self.assertLess((ROOT / "assets/hero.png").stat().st_size, 1_500_000)
        prompt = (ROOT / "docs/copy-prompt.txt").read_text()
        self.assertEqual(prompt, (ROOT / "site/setup-prompt.txt").read_text())
        payload = json.loads((ROOT / "site/scripts/setup-data.js").read_text().removeprefix("window.SF_SETUP = ").removesuffix(";\n"))
        for host in json.loads((ROOT / "site/hosts.json").read_text()):
            self.assertIn(payload[host]["prompt"].rstrip(), readme)
            self.assertIn(payload[host]["command"], payload[host]["prompt"])
            self.assertIn('--project "<this-project>"', payload[host]["command"])
            self.assertEqual(
                ["python3", "-I", "-B", "install.py", "install", "--host", host,
                 "--skip-bmad", "--project", "<this-project>", "--profile", "full", "--dry-run"],
                shlex.split(payload[host]["command"]),
            )
        for term in ("twenty", "GO", "eval", "BMad", "epic", "permission"):
            self.assertIn(term, prompt)
        self.assertNotIn("human epic checkpoint", prompt)

    def test_bootstrap_and_native_routes_keep_distinct_trust_and_namespaces(self):
        readme = README.read_text()
        routes = readme.split("## Choose the route that matches your goal\n", 1)[1].split("## The nine workflow maps", 1)[0]
        rows = {line.split(" | ", 1)[0].removeprefix("| "): line
                for line in routes.splitlines() if line.startswith("| ")}
        for row in rows.values():
            # GFM treats unescaped pipes as separators, even inside inline code.
            cells = re.split(r"(?<!\\)\|", row.strip("|"))
            self.assertEqual(3, len(cells), row)
        self.assertIn("Full project installation", rows)
        self.assertIn("Local bootstrap", rows)
        self.assertIn("Raw pinned skills acquisition", rows)
        self.assertIn("Native bundles", rows)
        self.assertIn('`sh "$SF_PACK/install.sh" --host "$SF_HOST" --project "$SF_PROJECT" --skip-bmad --dry-run`',
                      rows["Local bootstrap"])
        self.assertIn("without downloads, even if `--ref`", rows["Local bootstrap"])
        self.assertIn("docs/distribution.md#bootstrap", routes)
        self.assertIn(r'`cd "$SF_PROJECT" \|\| exit 1`', rows["Raw pinned skills acquisition"])
        self.assertIn('`DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 npx -y skills@1.7.2 add "$SF_PACK/skills" -a claude-code -a cursor -a codex -y`',
                      rows["Raw pinned skills acquisition"])
        self.assertIn("avoid discovering locally installed extras", rows["Raw pinned skills acquisition"])
        self.assertIn("BMad provisioning remains separate", rows["Raw pinned skills acquisition"])
        self.assertIn("`/software-factory:software-factory`", rows["Native bundles"])
        self.assertIn("full project setup uses `/software-factory`", rows["Native bundles"])
        self.assertNotIn("/software-factory:software-factory", rows["Full project installation"])
        self.assertNotIn("/software-factory:software-factory", rows["Raw pinned skills acquisition"])
        for term in ("separately downloaded and reviewed", "sf-TAG.tar.gz", "SHA256SUMS",
                     "explicit `--ref TAG`", "default `v0.1.0`", "never resolves `latest`",
                     "verified v0.1.0 pre-release", "same-origin checksum", "not an independent publisher signature",
                     "before its archive verification"):
            self.assertIn(term, routes)
        self.assertNotRegex(routes, r"curl[^\n]*\|\s*(?:sh|bash)")

    def test_comparison_dimensions_and_distinct_platform(self):
        readme = README.read_text()
        comparison = readme.split("## Where this fits\n", 1)[1].split("## One synthetic lap", 1)[0]
        rows = [line for line in comparison.splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(rows) - 2, 10)
        columns = [cell.strip() for cell in rows[0].strip("|").split("|")]
        self.assertEqual(["Capability", "Software Factory", "Superpowers", "BMad 6.12",
                          "Spec Kit", "Factory Missions", "eve template"], columns)
        for row in rows[2:]:
            self.assertEqual(len(columns), len(row.strip("|").split("|")), row)
        for pinned in ("bb92a77741419a4ab5f06e711a283343f1ada0c3",
                       "05bfbd46d00766ec88eb9b42e76be2c575d64d7b",
                       "3238fa9285694dc539aeb9829b337bfd6aed7317",
                       "6bc5febab95de4c05fa08b164f544650f6aa11aa"):
            self.assertIn(pinned, comparison)
        self.assertIn("https://docs.factory.com/missions/overview", comparison)
        self.assertIn("Not established", comparison)

    def test_readme_links_resolve_in_actual_release(self):
        output = self.base / "release"
        built = self.run_cli(PYTHON, "-B", ROOT / "scripts/build_release.py",
                             "--ref", "v0.1.0", "--out", output)
        self.assertEqual(0, built.returncode, built.stderr[-1000:])
        with tarfile.open(output / "sf-v0.1.0.tar.gz", "r:gz") as archive:
            files = {member.name.removeprefix("sf-v0.1.0/"): archive.extractfile(member).read()
                     for member in archive if member.isfile()}
        self.assertNotIn(".software-factory/context/board/roadmap.json", files)
        document = files["README.md"].decode("utf-8")
        self.assertEqual([], release_link_errors(document, files))
        self.assertIn("assets/hero.png", files)
        without_hero = dict(files)
        without_hero.pop("assets/hero.png")
        self.assertIn("released README links to absent assets/hero.png",
                      release_link_errors(document, without_hero))

    def test_three_fresh_consumers_preserve_bytes_and_repeat(self):
        readme = README.read_text()
        for host, skill, role in (("claude-code", ".claude/skills", ".claude/agents"),
                                  ("cursor", ".agents/skills", ".cursor/agents"),
                                  ("codex", ".agents/skills", ".codex/agents")):
            with self.subTest(host=host):
                project = self.consumer(host + " consumer with spaces")
                settings = {"claude-code": (".claude/settings.json", b'{"env":{"USER_CHOICE":"keep"}}\n'),
                            "cursor": (".cursor/hooks.json", b'{"version":1,"hooks":{"beforeShellExecution":[{"type":"command","command":"echo user"}]}}\n'),
                            "codex": (".codex/hooks.json", b'{"hooks":{"SessionStart":[{"matcher":"startup","hooks":[{"type":"command","command":"echo user"}]}]}}\n')}
                setting_name, setting_bytes = settings[host]
                setting = project / setting_name
                setting.parent.mkdir(parents=True, exist_ok=True)
                setting.write_bytes(setting_bytes)
                before = support.tree_hashes(project)
                argv = literal_argv(readme, host, ROOT, project)
                preview = self.run_cli(*argv)
                self.assertEqual(0, preview.returncode, preview.stderr[-1000:])
                self.assertEqual(before, support.tree_hashes(project))
                apply = self.run_cli(*argv[:-1])
                self.assertEqual(0, apply.returncode, apply.stderr[-1000:])
                self.assertTrue((project / skill / "software-factory/SKILL.md").is_file())
                self.assertTrue((project / role).is_dir())
                self.assertTrue((project / ".software-factory/runtime").is_dir())
                manifest = json.loads((project / ".software-factory/installation.json").read_text())
                self.assertEqual([host], manifest["hosts"])
                self.assertEqual("full", manifest["profile"])
                self.assertGreater(len(manifest["files"]), 50)
                for entry in manifest["files"]:
                    self.assertEqual(entry["sha256"], hashlib.sha256((project / entry["path"]).read_bytes()).hexdigest())
                after = support.tree_hashes(project)
                repeat = self.run_cli(*argv[:-1])
                self.assertEqual(0, repeat.returncode, repeat.stderr[-1000:])
                self.assertEqual(after, support.tree_hashes(project))
                for name in ("README.md", "CONVENTIONS.md", "user-settings.json"):
                    self.assertEqual(before[name], after[name])
                self.assertIn("USER_CHOICE" if host == "claude-code" else "echo user", setting.read_text())

    def test_controlled_doctor_is_read_only(self):
        project = self.consumer("doctor")
        argv = literal_argv(README.read_text(), "codex", ROOT, project)
        installed = self.run_cli(*argv[:-1])
        self.assertEqual(0, installed.returncode, installed.stderr[-1000:])
        before = support.tree_hashes(project)
        doctor = self.run_cli(PYTHON, "-I", "-B", ROOT / "install.py", "doctor",
                              "--project", project, "--json")
        self.assertIn(doctor.returncode, (0, 1), doctor.stderr[-1000:])
        report = json.loads(doctor.stdout)
        self.assertIsInstance(report, dict)
        self.assertEqual(before, support.tree_hashes(project))
        self.assertTrue(self.guard.exists(), "controlled gh stub should be consulted")
        controlled_doctor_log(self.guard.read_text(), self.stubs / "gh")
        with self.assertRaises(ValueError):
            controlled_doctor_log(self.guard.read_text() + f"{self.stubs / 'claude'} --version\n", self.stubs / "gh")
        self.guard.unlink()

    def test_foreign_and_edited_owned_refusals(self):
        readme = README.read_text()
        project = self.consumer("collision")
        foreign = project / ".agents/skills/software-factory/SKILL.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"user-owned skill\n")
        argv = literal_argv(readme, "codex", ROOT, project)
        result = self.run_cli(*argv[:-1])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b"user-owned skill\n", foreign.read_bytes())
        self.assertFalse((project / ".software-factory/installation.json").exists())
        foreign.unlink()
        self.assertEqual(0, self.run_cli(*argv[:-1]).returncode)
        foreign.write_bytes(b"edited owned skill\n")
        before = support.tree_hashes(project)
        refused = self.run_cli(*argv[:-1])
        self.assertNotEqual(0, refused.returncode)
        self.assertEqual(before, support.tree_hashes(project))

    def test_tampered_managed_block_refuses_without_rewrite(self):
        project = self.consumer("tampered-block")
        argv = literal_argv(README.read_text(), "claude-code", ROOT, project)
        installed = self.run_cli(*argv[:-1])
        self.assertEqual(0, installed.returncode, installed.stderr[-1000:])
        instructions = project / "CLAUDE.md"
        self.assertIn("<!-- software-factory:end -->", instructions.read_text())
        instructions.write_text(instructions.read_text().replace("<!-- software-factory:end -->", "", 1))
        before = support.tree_hashes(project)
        refused = self.run_cli(*argv[:-1])
        self.assertNotEqual(0, refused.returncode)
        self.assertEqual(before, support.tree_hashes(project))

    def test_missing_source_refuses_before_consumer_writes(self):
        source = self.base / "source"
        source.mkdir()
        for name in json.loads((ROOT / "hosts/plugins/release-files.json").read_text()):
            src = ROOT / name
            dest = source / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        project = self.consumer("missing-source")
        before = support.tree_hashes(project)
        argv = literal_argv(README.read_text(), "codex", source, project)
        preview = self.run_cli(*argv)
        self.assertEqual(0, preview.returncode, preview.stderr[-1000:])
        self.assertEqual(before, support.tree_hashes(project))
        (source / "templates/PRINCIPLES.md").unlink()
        refused = self.run_cli(*argv[:-1])
        self.assertNotEqual(0, refused.returncode)
        self.assertEqual(before, support.tree_hashes(project))


if __name__ == "__main__":
    unittest.main()
