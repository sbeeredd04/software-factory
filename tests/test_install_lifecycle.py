"""Config dependency shipping and truthful read-only BMad diagnostics."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support


class ConfigLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'project'
        shutil.copytree(support.REPO/'examples/config',self.repo)
        self.env,self.guard,stubs = support.guard_env()
        self.addCleanup(shutil.rmtree,stubs,ignore_errors=True)
        self.auth_log = self.base / 'fixture-auth.log'
        self.env['SF_FIXTURE_AUTH_LOG'] = str(self.auth_log)
        gh = stubs / 'gh'
        gh.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$SF_FIXTURE_AUTH_LOG"\nexit 1\n')
        gh.chmod(0o755)
        self.env['HOME'] = str(self.base/'home')
        Path(self.env['HOME']).mkdir()
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'

    def tearDown(self):
        self.assertFalse(self.guard.exists())

    def test_installed_runtime_and_skills_validate_without_source_checkout(self):
        result = support.run_installer('install','--project',self.repo,'--host','all','--skip-bmad',env=self.env)
        self.assertEqual(0,result.returncode,result.stderr)
        for rel in ('.software-factory/runtime/config.py','.claude/skills/software-factory/scripts/config.py','.agents/skills/software-factory/scripts/config.py'):
            before = support.tree_hashes(self.repo)
            run = subprocess.run([sys.executable,str(self.repo/rel),'validate','--config',str(self.repo/'config.yaml')],cwd=self.base,env=self.env,capture_output=True,text=True,check=False)
            self.assertEqual(0,run.returncode,run.stderr)
            self.assertEqual(before,support.tree_hashes(self.repo))

    def test_native_bundles_include_canonical_schema_and_tracker(self):
        out = self.base / 'bundles'
        result = subprocess.run([sys.executable,str(support.REPO/'scripts/distribution.py'),'--host','all','--out',str(out)],env=self.env,capture_output=True,text=True,check=False)
        self.assertEqual(0,result.returncode,result.stderr)
        for host in ('claude-code','cursor','codex'):
            bundle = out/host/'plugins/software-factory'
            self.assertEqual((support.REPO/'schemas/config.schema.json').read_bytes(),(bundle/'skills/software-factory/schemas/config.schema.json').read_bytes())
            self.assertEqual((support.REPO/'adapters/trackers.py').read_bytes(),(bundle/'skills/software-factory/scripts/trackers.py').read_bytes())
            result = subprocess.run([sys.executable,str(bundle/'scripts/config.py'),'--config',str(self.repo/'config.yaml')],env=self.env,capture_output=True,text=True,check=False)
            self.assertEqual(0,result.returncode,result.stderr)

    def test_bmad_missing_partial_valid_and_failed_record(self):
        result = support.run_installer('install','--project',self.repo,'--host','cursor','--skip-bmad',env=self.env)
        self.assertEqual(0,result.returncode,result.stderr)
        manifest = self.repo/'_bmad/_config/manifest.yaml'
        def observation():
            before = support.tree_hashes(self.repo)
            result = support.run_installer('doctor','--project',self.repo,'--json',env=self.env)
            self.assertEqual(before,support.tree_hashes(self.repo))
            return next(c for c in json.loads(result.stdout)['checks'] if c['name']=='bmad')
        self.assertEqual('unverified',observation()['status'])
        manifest.parent.mkdir(parents=True)
        manifest.write_text('broken: [')
        self.assertEqual('warning',observation()['status'])
        manifest.write_text(json.dumps({'installation':{'version':'6.12.0'},'modules':['core'],'ides':['cursor']}))
        self.assertEqual('pass',observation()['status'])
        ownership = self.repo/'.software-factory/installation.json'
        data = json.loads(ownership.read_text())
        data['bmad'] = {'status':'failed','manifest_sha256':'0'*64}
        ownership.write_text(json.dumps(data))
        self.assertEqual('warning',observation()['status'])
        self.assertEqual(['auth status'] * 4, self.auth_log.read_text().splitlines())
