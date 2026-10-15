"""Native bundles: deterministic, contained, relocatable and policy-preserving."""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import REPO, Workspace, guard_env, tree_hashes

sys.path.insert(0, str(REPO / 'scripts'))
import build_release
import check_distribution as checks
import distribution as dist


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = dist.load_api()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def bundle(self, host='claude-code', name='bundle'):
        return dist.project(self.api, host, self.root / name)

    def test_all_hosts_reproducible_bytes_paths_modes(self):
        for host in dist.HOSTS:
            with self.subTest(host=host):
                one, two = self.bundle(host, host+'1'), self.bundle(host, host+'2')
                self.assertEqual(tree_hashes(one), tree_hashes(two))
                modes = lambda root: {p.relative_to(root).as_posix(): p.stat().st_mode & 0o777
                                      for p in root.rglob('*')}
                self.assertEqual(modes(one), modes(two))
                self.assertTrue(checks.check(one, host, self.api))
                for path in one.rglob('*'):
                    self.assertNotIn(path.name, ('settings.json', 'CLAUDE.md', 'AGENTS.md', '.software-factory'))
                    if path.is_file():
                        self.assertNotIn(str(REPO).encode(), path.read_bytes())
                        self.assertNotIn(str(Path.home()).encode(), path.read_bytes())

    def test_explicit_six_working_five_each_host(self):
        for host in dist.HOSTS:
            root = self.bundle(host, host) / dist.PLUGIN
            explicit = set(self.api.load_policy(host)['explicit_only'])
            self.assertEqual(len(explicit), 6)
            for skill in (root / 'skills').iterdir():
                text = (skill / 'SKILL.md').read_text()
                if host == 'codex':
                    path = skill / 'agents/openai.yaml'
                    if skill.name in explicit:
                        self.assertIn('allow_implicit_invocation: false', path.read_text())
                else:
                    self.assertEqual('disable-model-invocation: true' in text, skill.name in explicit)
            self.assertEqual(len(list((root / ('role-prompts' if host == 'codex' else 'agents')).glob('sf-*'))), 11)

    def test_all_layout_and_no_host_invocations(self):
        env, log, guards = guard_env()
        self.addCleanup(shutil.rmtree, guards)
        before = tree_hashes(REPO)
        result = subprocess.run([sys.executable, str(REPO/'install.py'), 'project', '--host', 'all',
                                 '--out', str(self.root/'all')], env=env, check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, tree_hashes(REPO))
        self.assertFalse(log.exists())
        for host in dist.HOSTS:
            checks.check(self.root/'all'/host, host, self.api)

    def test_existing_output_and_unsafe_paths_preserved(self):
        existing = self.root/'existing'
        existing.mkdir()
        (existing/'sentinel').write_text('keep')
        link = self.root/'link'
        link.symlink_to(existing, target_is_directory=True)
        for path in (existing, link/'new', self.root/'missing'/'new', REPO/'new', REPO, REPO.parent):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.bundle(name=str(path))
        self.assertEqual((existing/'sentinel').read_text(), 'keep')
        self.assertEqual(list(existing.iterdir()), [existing/'sentinel'])

    def test_write_failure_and_interrupt_remove_partial_tree(self):
        for error in (OSError('fixture write failure'), KeyboardInterrupt()):
            with (patch.object(Path, 'write_bytes', side_effect=error),
                  self.assertRaises(type(error))):
                self.bundle()
            self.assertFalse((self.root/'bundle').exists())

    def test_source_symlink_refused(self):
        root = self.root/'source'
        root.mkdir()
        (root/'skills').symlink_to(REPO/'skills')
        with self.assertRaises(ValueError):
            dist.safe_sources(root)

    def test_manifest_rejects_bad_paths_missing_components_and_policy_drift(self):
        for host in dist.HOSTS:
            for value in ('../escape', '/absolute', './missing'):
                bundle = self.bundle(host, host+str(len(list(self.root.iterdir()))))
                catalog = bundle/dist.CATALOGS[host]
                data = json.loads(catalog.read_text())
                data['plugins'][0]['source'] = ({'source':'local','path':value} if host == 'codex' else value)
                catalog.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    checks.check(bundle, host, self.api)
        bundle = self.bundle('codex')
        policy = bundle/dist.PLUGIN/'skills/software-factory/agents/openai.yaml'
        policy.write_text('policy:\n  allow_implicit_invocation: true\n')
        with self.assertRaises(ValueError):
            checks.check(bundle, 'codex', self.api)

    def test_portable_schema_rejects_native_fields_and_invalid_types(self):
        schema = checks.json_file(REPO/'schemas/plugins/portable.schema.json')
        original = checks.json_file(REPO/'plugin.json')
        for update in ({'skills':['./skills']}, {'author': 'wrong'}, {'name': 'claude--fake'}, {'extensions': {'com.openai': []}}):
            with self.assertRaises(ValueError):
                checks.schema_check(dict(original, **update), schema)

    def test_symlink_escape_rejected(self):
        bundle = self.bundle()
        target = bundle/dist.PLUGIN/'agents/sf-engineer.md'
        target.unlink()
        target.symlink_to(REPO/'agents/sf-engineer.md')
        with self.assertRaises(ValueError):
            checks.check(bundle, 'claude-code', self.api)

    def test_relocated_hooks_consumer_state_and_python_fail_soft(self):
        workspace = Workspace()
        self.addCleanup(workspace.cleanup)
        for host in dist.HOSTS:
            bundle = self.bundle(host, host)
            moved = self.root/(host+' relocated with spaces')
            bundle.rename(moved)
            plugin = moved/dist.PLUGIN
            config = json.loads((plugin/'hooks/hooks.json').read_text())
            event = 'sessionStart' if host == 'cursor' else 'SessionStart'
            entry = config['hooks'][event][0]
            command = (entry if host == 'cursor' else entry['hooks'][0])['command']
            env = dict(os.environ, PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],
                       CLAUDE_PLUGIN_ROOT=str(plugin), CURSOR_PLUGIN_ROOT=str(plugin), PLUGIN_ROOT=str(plugin))
            payload = {'workspace_roots':[str(workspace.root)]} if host == 'cursor' else {'cwd':str(workspace.root)}
            before = tree_hashes(plugin)
            result = subprocess.run(['sh','-c',command], input=json.dumps(payload), cwd=self.root,
                                    env=env, text=True, check=False, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('recovery pointer', result.stdout)
            self.assertEqual(before, tree_hashes(plugin))
            inactive = {'workspace_roots':[str(self.root)]} if host == 'cursor' else {'cwd':str(self.root)}
            result = subprocess.run(['sh','-c',command], input=json.dumps(inactive), cwd=self.root,
                                    env=env, text=True, check=False, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            for old in (True, False):
                bins = self.root/(host+str(old))
                bins.mkdir()
                if old:
                    stub = bins/'python3'
                    stub.write_text('#!/bin/sh\nexit 1\n')
                    stub.chmod(0o755)
                bad_env = dict(env, PATH=str(bins))
                result = subprocess.run(['/bin/sh',str(plugin/'scripts/hook.sh'),'--host',host,'--event','session-start'],
                                        input=json.dumps(payload), env=bad_env, text=True, check=False, capture_output=True)
                self.assertEqual(result.returncode, 0)
                self.assertIn('Python 3.11', result.stdout)

    def test_cli_fresh_source_writes_only_output(self):
        source = self.root/'fresh source'
        source.mkdir()
        for name, data in build_release.release_files(self.api).items():
            if name.startswith('dist/'):
                continue
            path = source/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        home = self.root/'home'
        home.mkdir()
        (home/'sentinel').write_text('untouched')
        caller = self.root/'caller'
        caller.mkdir()
        before = tree_hashes(source), tree_hashes(home), tree_hashes(caller)
        env, log, guards = guard_env()
        self.addCleanup(shutil.rmtree, guards)
        env['HOME'] = str(home)
        for host in (*dist.HOSTS, 'all'):
            result = subprocess.run([sys.executable,str(source/'install.py'),'project','--host',host,
                                     '--out',str(self.root/('fresh-'+host))], cwd=caller, env=env,
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, (tree_hashes(source),tree_hashes(home),tree_hashes(caller)))
        self.assertFalse(list(source.rglob('__pycache__')))
        self.assertFalse(log.exists())

    def release_source(self):
        source = self.root/'release source'
        source.mkdir()
        for name, data in build_release.release_files(self.api).items():
            if not name.startswith('dist/'):
                path = source/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        return dist.load_api(source)

    def test_release_native_payload_excludes_unlisted_local_files(self):
        api = self.release_source()
        baseline = build_release.release_files(api)
        marker = b'UNLISTED_RELEASE_SENTINEL'
        for name in ('skills/software-factory/.env',
                     'skills/software-factory/references/private-notes.md'):
            (api.PACK_ROOT/name).write_bytes(marker)
        files = build_release.release_files(api)
        self.assertEqual(files, baseline)
        archive = build_release.archive_bytes(files, 'v'+api.PACK_VERSION)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as payload:
            for member in payload:
                self.assertNotIn('private-notes', member.name)
                self.assertNotEqual(Path(member.name).name, '.env')
                self.assertNotIn(marker, payload.extractfile(member).read())

    def test_native_release_uses_captured_bytes_after_source_changes(self):
        api = self.release_source()
        baseline = build_release.release_files(api)
        projector = dist.bundle_files

        def change_live_source_then_project(snapshot_api, host):
            self.assertNotEqual(snapshot_api.PACK_ROOT, api.PACK_ROOT)
            (api.PACK_ROOT/'skills/software-factory/references/late-note.md').write_text('LATE_SENTINEL')
            (api.PACK_ROOT/'skills/software-factory/SKILL.md').write_text('CHANGED_SENTINEL')
            return projector(snapshot_api, host)

        with patch.object(dist, 'bundle_files', side_effect=change_live_source_then_project):
            files = build_release.release_files(api)
        self.assertEqual(files, baseline)

    def test_release_reproducible_and_allowlisted(self):
        one = build_release.build(self.api, self.root/'release1', 'v'+self.api.PACK_VERSION)
        two = build_release.build(self.api, self.root/'release2', 'v'+self.api.PACK_VERSION)
        self.assertEqual(tree_hashes(one), tree_hashes(two))
        files = build_release.release_files(self.api)
        self.assertIn('install.py', files)
        self.assertFalse(any('.software-factory/' in p or '__pycache__' in p or p.startswith('.git') for p in files))
        self.assertTrue(all('dist/plugins/'+h+'/'+dist.CATALOGS[h] in files for h in dist.HOSTS))
        with self.assertRaises(ValueError):
            build_release.build(self.api, self.root/'bad', 'v999.0.0')


if __name__ == '__main__':
    unittest.main()
