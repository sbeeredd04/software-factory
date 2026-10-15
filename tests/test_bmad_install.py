"""Pinned provisioning, preserved third-party state and honest failure proof."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import runpy
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support

spec = importlib.util.spec_from_file_location("sf_bmad", support.REPO / "scripts/bmad_install.py")
bmad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bmad)

MANIFEST = """installation:
  version: 6.12.0
  installDate: 2026-01-01T00:00:00.000Z
  installShims: false
modules:
  - name: core
    version: 6.12.0
    source: built-in
  - name: bmm
    version: 6.12.0
  - name: bmb
    version: v2.4.1
    source: external
    channel: stable
    sha: abc123
  - name: cis
    version: v0.8.0
    sha: null
  - name: tea
    version: null
ides:
  - claude-code
  - cursor
  - codex
"""

STUB = r'''
import csv,json,os,sys,time
from pathlib import Path
name=Path(sys.argv[0]).name
log=Path(os.environ['SF_BMAD_LOG'])
with log.open('a') as stream:
    stream.write(json.dumps({'name':name,'argv':sys.argv[1:],'stdin':sys.stdin.read(),'cwd':os.getcwd()})+'\n')
if name=='node':
    print(os.environ.get('SF_NODE_VERSION','v20.12.0'))
    sys.exit(0)
if name=='npm':
    print('10.8.2')
    sys.exit(0)
if name!='npx':
    sys.exit(99)
root=Path(sys.argv[sys.argv.index('--directory')+1])
metadata=root/'.software-factory/installation.json'
if metadata.is_file():
    assert json.loads(metadata.read_text())['bmad']['status']=='failed'
mode=os.environ.get('SF_BMAD_MODE','success')
if mode=='sleep':
    time.sleep(30)
if mode=='none':
    sys.exit(0)
(root/'_bmad/core').mkdir(parents=True,exist_ok=True)
(root/'_bmad/core/partial.txt').write_text('partial upstream work')
if mode=='fail':
    print('PRIVATE-VALUE must never be printed by the wrapper',file=sys.stderr)
    sys.exit(17)
(root/'_bmad/bmm').mkdir(exist_ok=True)
(root/'_bmad/_config').mkdir(exist_ok=True)
(root/'_bmad/_config/manifest.yaml').write_text(os.environ['SF_BMAD_MANIFEST'] if mode!='malformed' else '!unsafe object')
with (root/'_bmad/_config/skill-manifest.csv').open('w',newline='') as stream:
    writer=csv.writer(stream)
    writer.writerow(['canonicalId','name','description','module','path'])
    for module in ('core','bmm','bmb','cis','tea'):
        skill_id='bmad-fixture-'+module
        writer.writerow([skill_id,skill_id,'Synthetic skill',module,'_bmad/'+module+'/SKILL.md'])
        for base in ('.claude/skills','.agents/skills'):
            if mode=='incomplete-module' and module=='tea':
                continue
            skill=root/base/skill_id/'SKILL.md'
            skill.parent.mkdir(parents=True,exist_ok=True)
            skill.write_text('# Synthetic BMad skill\n')
if mode=='conflict':
    (root/'.agents/skills/software-factory/SKILL.md').write_text('upstream collision')
if mode in ('projection-fifo','manifest-fifo'):
    target=(root/'.agents/skills/software-factory/SKILL.md') if mode=='projection-fifo' else metadata
    target.unlink()
    os.mkfifo(target)
'''


class BmadTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sf-bmad-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.repo = support.fresh_repo(self.temp, "project with spaces")
        self.env, self.guard, self.bin = support.guard_env()
        self.addCleanup(shutil.rmtree, self.bin, ignore_errors=True)
        self.home, self.snapshot_home = support.home_sentinel(self.temp)
        self.env.update(HOME=str(self.home), PATH=str(self.bin), SF_BMAD_LOG=str(self.temp / "calls.jsonl"),
                        SF_BMAD_MANIFEST=MANIFEST, PYTHONDONTWRITEBYTECODE="1")
        self.home_before = self.snapshot_home()
        for name in bmad.PREREQUISITES:
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n" + STUB)
            path.chmod(0o755)

    def tearDown(self):
        self.assertFalse(self.guard.exists())
        self.assertEqual(self.home_before, self.snapshot_home())

    def calls(self):
        path = Path(self.env["SF_BMAD_LOG"])
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def install(self, host="all", *args):
        result = support.run_installer("install", "--project", self.repo, "--host", host, *args, env=self.env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("PRIVATE-VALUE", result.stdout + result.stderr)
        return result

    def record(self):
        return json.loads((self.repo / ".software-factory/installation.json").read_text())["bmad"]

    def assert_factory(self):
        data = json.loads((self.repo / ".software-factory/installation.json").read_text())
        for entry in data["files"]:
            self.assertFalse(entry["path"].startswith("_bmad/") or "/skills/bmad-" in entry["path"])
            self.assertTrue((self.repo / entry["path"]).is_file())
        return data

    def test_missing_prerequisites_degrade_without_any_probe(self):
        for name in ("node", "npx", "uv"):
            (self.bin / name).unlink()
        result = self.install()
        self.assertEqual("degraded", self.record()["status"])
        for term in ("Node >=20.12", "npx", "uv", "install"):
            self.assertIn(term, result.stdout)
        self.assertEqual([], self.calls())
        self.assertFalse((self.repo / "_bmad").exists())
        self.assert_factory()

    def test_old_node_stops_before_npm_or_npx(self):
        self.env["SF_NODE_VERSION"] = "v18.19.0"
        self.install()
        self.assertEqual(["node"], [c["name"] for c in self.calls()])
        self.assertEqual("degraded", self.record()["status"])
        self.assertEqual("v18.19.0", self.record()["runtime_versions"]["node"])
        self.assertFalse((self.repo / "_bmad").exists())

    def test_exact_argv_each_host_and_actual_versions(self):
        for host in ("claude-code", "cursor", "codex", "all"):
            with self.subTest(host=host):
                self.repo = support.fresh_repo(self.temp, "project with spaces " + host)
                before = len(self.calls())
                self.install(host)
                calls = self.calls()[before:]
                self.assertEqual(["node", "npm", "npx"], [c["name"] for c in calls])
                tools = {"claude-code": "claude-code", "cursor": "cursor", "codex": "codex",
                         "all": "claude-code,cursor,codex"}[host]
                self.assertEqual([
                    "-y", "bmad-method@6.12.0", "install", "--directory", str(self.repo),
                    "--tools", tools, "--modules", "bmm,bmb,cis,tea", "--yes",
                ], calls[-1]["argv"])
                self.assertEqual(str(self.repo), calls[-1]["cwd"])
                self.assertEqual("", calls[-1]["stdin"])
                record = self.record()
                self.assertEqual("installed", record["status"])
                self.assertEqual({"node": "v20.12.0", "npm": "10.8.2"}, record["runtime_versions"])
                self.assertEqual(bmad.parse_manifest(MANIFEST.encode())["modules"], record["modules"])
                self.assert_factory()

    def test_output_verification_has_skill_count_and_aggregate_budgets(self):
        record = bmad.parse_manifest(MANIFEST.encode())
        header = "canonicalId,name,description,module,path\n"
        oversized = header + "".join(
            f"bmad-fixture-{index},fixture,fixture,core,unused\n"
            for index in range(bmad.MAX_SKILLS + 1)
        )
        with mock.patch.object(bmad, "read_payload", return_value=oversized.encode()) as read:
            self.assertFalse(bmad.complete(self.repo, ["codex"], record))
            self.assertEqual(1, read.call_count)  # Reject inventory before reading skills.
        inventory = (header + "".join(
            f"bmad-fixture-{module},fixture,fixture,{module},unused\n" for module in bmad.MODULES
        )).encode()
        limits = []

        def payload(root, rel, limit):
            if rel.endswith("skill-manifest.csv"):
                return inventory
            limits.append(limit)
            return b"x" * limit

        with (mock.patch.object(bmad, "MAX_VERIFICATION_BYTES", len(inventory) + 7),
              mock.patch.object(bmad, "read_payload", side_effect=payload)):
            self.assertFalse(bmad.complete(self.repo, ["claude-code", "codex"], record))
        self.assertEqual([7], limits)  # Stop before a second host read after exhaustion.

    def test_existing_manifest_preserved_without_probes_or_updates(self):
        path = self.repo / bmad.MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text(MANIFEST.replace("6.12.0", "5.9.0"))
        before = support.tree_hashes(self.repo / "_bmad")
        result = self.install()
        for term in ("5.9.0", "core=5.9.0", "bmb=v2.4.1", "claude-code", "cursor", "codex"):
            self.assertIn(term, result.stdout)
        self.assertEqual(before, support.tree_hashes(self.repo / "_bmad"))
        self.assertEqual([], self.calls())
        self.assertEqual("existing", self.record()["status"])
        self.assertEqual("5.9.0", self.record()["version"])
        snapshot = support.tree_hashes(self.repo)
        self.install()
        self.assertEqual(snapshot, support.tree_hashes(self.repo))

    def test_untrusted_metadata_is_recorded_but_not_echoed(self):
        path = self.repo / bmad.MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text(MANIFEST.replace("6.12.0", "PRIVATE-VALUE").replace("  - cursor", "  - PRIVATE-VALUE"))
        result = self.install()
        self.assertNotIn("PRIVATE-VALUE", result.stdout + result.stderr)
        self.assertIn("observed version unknown", result.stdout)
        self.assertEqual("PRIVATE-VALUE", self.record()["version"])

    def test_partial_malformed_and_alternative_artifacts_preserved(self):
        for index, rel in enumerate((bmad.MANIFEST, "_bmad/core/config.yaml",
                                     ".agents/skills/bmad-custom/SKILL.md", ".claude/commands/bmad.md")):
            with self.subTest(rel=rel):
                self.repo = support.fresh_repo(self.temp, f"partial-{index}")
                path = self.repo / rel
                path.parent.mkdir(parents=True)
                path.write_text("unparseable existing user artifact")
                self.install()
                self.assertEqual("unparseable existing user artifact", path.read_text())
                self.assertEqual("existing", self.record()["status"])
                self.assertIsNone(self.record()["version"])
                self.assertEqual([], self.calls())

    def test_skip_and_dry_run_have_zero_discovery_probes_and_spawns(self):
        api = runpy.run_path(str(support.INSTALLER))
        options = types.SimpleNamespace(project=self.repo, host="all", allow_overwrite=[],
                                        profile="full", dry_run=True, skip_bmad=False)
        with (mock.patch("importlib.util.spec_from_file_location", side_effect=AssertionError("BMad module loaded")),
              redirect_stdout(io.StringIO())):
            before = support.tree_hashes(self.repo)
            self.assertEqual(0, api["cmd_install"](options))
            self.assertEqual(before, support.tree_hashes(self.repo))
            options.dry_run, options.skip_bmad = False, True
            self.assertEqual(0, api["cmd_install"](options))
        self.assertEqual([], self.calls())
        self.assertNotIn("bmad", self.assert_factory())
        self.assertFalse((self.repo / "_bmad").exists())

    def test_failures_preserve_partial_outputs_and_do_not_retry(self):
        for mode in ("fail", "none", "malformed", "incomplete-module"):
            with self.subTest(mode=mode):
                self.repo = support.fresh_repo(self.temp, mode)
                self.env["SF_BMAD_MODE"] = mode
                self.install()
                self.assertEqual("failed", self.record()["status"])
                if mode != "none":
                    self.assertEqual("partial upstream work", (self.repo / "_bmad/core/partial.txt").read_text())
                count = len(self.calls())
                self.install()
                self.assertEqual(count, len(self.calls()))
                self.assert_factory()

    def test_interruption_receipt_prevents_implicit_retry(self):
        self.install("all", "--skip-bmad")
        api = types.SimpleNamespace(**runpy.run_path(str(support.INSTALLER)))
        with (mock.patch.dict(os.environ, self.env, clear=True),
              mock.patch.object(bmad, "invoke", side_effect=KeyboardInterrupt),
              self.assertRaises(KeyboardInterrupt)):
            bmad.provision(self.repo, ["cursor"], api)
        self.assertEqual("failed", self.record()["status"])
        self.assertIn("completion unverified", self.record()["reason"])
        count = len(self.calls())
        self.install()
        self.assertEqual(count, len(self.calls()))

    def test_timeout_terminates_attempt_and_is_not_success(self):
        self.env["SF_BMAD_MODE"] = "sleep"
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(bmad, "INSTALL_TIMEOUT", 0.1):
            record = bmad.attempt(self.repo, ["cursor"])
        self.assertEqual("failed", record["status"])
        self.assertIn("timed out", record["reason"])
        self.assertIsNone(record["exit_code"])

    def test_upstream_factory_collision_is_reported_without_discarding_evidence(self):
        self.env["SF_BMAD_MODE"] = "conflict"
        result = support.run_installer("install", "--project", self.repo, "--host", "all", env=self.env)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("failed", self.record()["status"])
        self.assertIn("factory-owned files changed", self.record()["reason"])
        self.assertEqual("upstream collision", (self.repo / ".agents/skills/software-factory/SKILL.md").read_text())
        self.assertTrue((self.repo / bmad.MANIFEST).is_file())

    def test_metadata_survives_skip_update_host_addition_and_uninstall(self):
        self.install("cursor")
        original = self.record()
        self.install("codex", "--skip-bmad")
        self.assertEqual(original, self.record())
        bmad_before = support.tree_hashes(self.repo / "_bmad")
        result = support.run_installer("uninstall", "--project", self.repo, env=self.env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(bmad_before, support.tree_hashes(self.repo / "_bmad"))
        self.assertTrue((self.repo / ".agents/skills/bmad-fixture-core/SKILL.md").is_file())

    def test_unsafe_ownership_paths_are_refused_before_upstream_or_payload_reads(self):
        self.install("all", "--skip-bmad")
        api = types.SimpleNamespace(**runpy.run_path(str(support.INSTALLER)))
        path = self.repo / ".software-factory/installation.json"
        original = json.loads(path.read_text())
        for unsafe in ("../outside", str(self.temp / "outside"), "", ".", "x/../outside", "x//file"):
            with self.subTest(path=unsafe):
                data = json.loads(json.dumps(original))
                data["files"][0]["path"] = unsafe
                path.write_text(json.dumps(data))
                with (mock.patch.object(bmad, "attempt", side_effect=AssertionError("upstream")),
                      mock.patch.object(bmad, "read_payload", wraps=bmad.read_payload) as reads,
                      self.assertRaises(api.InstallError)):
                    bmad.provision(self.repo, ["cursor"], api)
                self.assertEqual([api.MANIFEST_REL], [call.args[1] for call in reads.call_args_list])

    def test_final_component_replacement_is_not_followed_and_is_reported_unstable(self):
        target = self.repo / "payload"
        target.write_bytes(b"original")
        outside = self.temp / "outside"
        outside.write_bytes(b"external private bytes")
        original_fdopen = bmad.os.fdopen

        def replace_before_read(*args, **kwargs):
            target.unlink()
            target.symlink_to(outside)
            return original_fdopen(*args, **kwargs)

        with (mock.patch.object(bmad.os, "fdopen", side_effect=replace_before_read),
              self.assertRaisesRegex(ValueError, "changed during observation")):
            bmad.read_payload(self.repo, "payload", 100)
        self.assertEqual(b"external private bytes", outside.read_bytes())
        with self.assertRaises(OSError):
            bmad.read_payload(self.repo, "payload", 100)

    def test_oversized_ownership_manifest_is_refused_before_upstream(self):
        self.install("all", "--skip-bmad")
        api = types.SimpleNamespace(**runpy.run_path(str(support.INSTALLER)))
        (self.repo / api.MANIFEST_REL).write_bytes(b" " * (bmad.MAX_OWNERSHIP_BYTES + 1))
        with (mock.patch.object(bmad, "attempt", side_effect=AssertionError("upstream")),
              self.assertRaises(api.InstallError)):
            bmad.provision(self.repo, ["cursor"], api)

    def test_upstream_special_files_cannot_block_verification_or_metadata_publication(self):
        for mode in ("projection-fifo", "manifest-fifo"):
            with self.subTest(mode=mode):
                self.repo = support.fresh_repo(self.temp, mode)
                self.env["SF_BMAD_MODE"] = mode
                result = support.run_installer("install", "--project", self.repo, "--host", "all",
                                               env=self.env, timeout=5)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertNotIn("Traceback", result.stdout + result.stderr)
                if mode == "projection-fifo":
                    self.assertEqual("failed", self.record()["status"])
                    self.assertIn("factory-owned files changed", self.record()["reason"])
                else:
                    self.assertIn("BMad metadata phase failed", result.stderr)

    def test_parser_subset_legacy_unknown_and_rejections(self):
        parsed = bmad.parse_manifest(b"installation:\n  version: '6.12.0'\nmodules:\n  - core\nides: []\n")
        self.assertEqual([{"name": "core", "version": None}], parsed["modules"])
        for malformed in (b"!tag value", b"installation: &x {}", MANIFEST.encode().replace(b"  version: 6.12.0", b"  version: 6.12.0\n  version: 6.12.0", 1),
                          b" " * (bmad.MAX_MANIFEST_BYTES + 1), b'{"installation":{},"installation":{},"modules":[],"ides":[]}'):
            with self.subTest(malformed=malformed[:40]), self.assertRaises((ValueError, TypeError)):
                bmad.parse_manifest(malformed)

    def test_symlinked_manifest_and_fifo_are_preserved_without_reading_targets(self):
        external = self.temp / "external"
        external.write_text(MANIFEST)
        manifest = self.repo / bmad.MANIFEST
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(external)
        self.install()
        self.assertIsNone(self.record()["version"])
        self.assertEqual([], self.calls())
        manifest.unlink()
        os.mkfifo(manifest)
        self.install()
        self.assertEqual([], self.calls())


@unittest.skipIf(os.environ.get("SF_SKIP_NETWORK") == "1", "network installer unverified (SF_SKIP_NETWORK=1)")
class OfficialInstallerTest(unittest.TestCase):
    def test_pinned_official_installer_in_disposable_project(self):
        if any(shutil.which(name) is None for name in bmad.PREREQUISITES):
            self.skipTest("network installer unverified: required executables unavailable")
        with tempfile.TemporaryDirectory(prefix="sf-bmad-network-") as temp:
            base = Path(temp).resolve()
            repo = support.fresh_repo(base)
            env, guard, stubs = support.guard_env()
            self.addCleanup(shutil.rmtree, stubs, ignore_errors=True)
            home = base / "home"
            home.mkdir()
            env.update(HOME=str(home), npm_config_cache=str(base / "npm-cache"),
                       npm_config_userconfig=str(base / "npmrc"), PYTHONDONTWRITEBYTECODE="1")
            result = support.run_installer("install", "--project", repo, "--host", "all", env=env, timeout=420)
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads((repo / ".software-factory/installation.json").read_text())
            saved = data["bmad"]
            # Wrapper success is factory success, never evidence of BMad success.
            self.assertTrue((repo / ".agents/skills/software-factory/SKILL.md").is_file())
            self.assertFalse(guard.exists())
            self.assertEqual("installed", saved["status"], saved["reason"])
            actual, parsed = bmad.observe(repo)
            self.assertTrue(parsed)
            self.assertEqual(actual["modules"], saved["modules"])
            self.assertEqual("6.12.0", saved["version"])
            # Separately observe BMad-only effects before factory directories exist.
            bmad_only = support.fresh_repo(base, "bmad-only")
            with mock.patch.dict(os.environ, env, clear=True):
                record = bmad.attempt(bmad_only, ["claude-code", "cursor", "codex"])
            self.assertEqual("installed", record["status"], record["reason"])
            self.assertFalse((bmad_only / ".cursor").exists())
            self.assertFalse((bmad_only / ".codex").exists())
            self.assertFalse(guard.exists())
