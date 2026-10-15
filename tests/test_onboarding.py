"""Synthetic setup/discovery proofs; no live host or model capability claims."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

SCRIPT = support.REPO/'skills/sf-help/scripts'
spec = importlib.util.spec_from_file_location('sf_onboarding_setup',SCRIPT/'setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
discover = setup.discover
FIXTURES = support.REPO/'tests/fixtures/onboarding'


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base/'project'
        self.root.mkdir()
        self.env,self.guard,stubs = support.guard_env()
        self.addCleanup(shutil.rmtree,stubs,ignore_errors=True)
        self.env['HOME'] = str(self.base/'home')
        Path(self.env['HOME']).mkdir()
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'

    def tearDown(self):
        self.assertFalse(self.guard.exists(),'forbidden host CLI invoked')

    def cli(self, name, *args):
        return subprocess.run([sys.executable,str(SCRIPT/name),'--project',str(self.root),*map(str,args)],env=self.env,capture_output=True,text=True,check=False)

    def proposal(self):
        return setup.propose(self.root)

    def crawl_fixture(self):
        path = self.root/discover.CRAWL
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('# Synthetic crawl fixture\nNo runtime or remote proof.\n')

    def approve(self,p):
        return setup.apply(self.root,p,p['sha256'],'owner-decision:setup-fixture')

    def test_new_defaults_are_adaptive_bmad_and_existing_profile_is_preserved(self):
        proposal = self.proposal()
        self.assertEqual('risk-adaptive', proposal['config']['autonomy']['mode'])
        self.assertTrue(proposal['config']['autonomy']['commits'])
        self.assertFalse(proposal['config']['checkpoints']['manual'])
        self.assertEqual('bmad', proposal['config']['planning']['method'])
        for action in ('push', 'open_pr', 'merge_integration', 'deploy'):
            self.assertFalse(proposal['config']['autonomy'][action])
        self.assertEqual(20, len(proposal['answers']))
        self.assertEqual('unknown', proposal['answers'][18]['state'])
        proposal['config']['planning']['method'] = 'native'
        proposal['config']['autonomy'].pop('mode')
        proposal['config']['checkpoints']['manual'] = True
        draft = setup.propose(self.root, draft=proposal['config'])
        self.approve(draft)
        original = (self.root / discover.CONFIG).read_bytes()
        reused = self.proposal()
        self.assertEqual('sf-setup-reuse/1', reused['schema'])
        self.assertEqual(original, (self.root / discover.CONFIG).read_bytes())

    def test_exact_twenty_catalog_groups_and_all_keys_exist(self):
        rows = setup.catalog()
        self.assertEqual(list(range(1,21)),[q['id'] for q in rows])
        self.assertEqual(list('AAAAABBBBCCCCDDDDEEE'),[q['group'] for q in rows])
        schema = discover.config.load(support.REPO/'schemas/config.schema.json')
        def properties(node):
            if '$ref' in node:
                node = schema['$defs'][node['$ref'].split('/')[-1]]
            found = dict(node.get('properties',{}))
            for branch in node.get('oneOf',[]):
                found.update(properties(branch))
            return found
        for row in rows:
            self.assertTrue(row['why'] and row['default'])
            for key in row['keys'].split(', '):
                node = schema
                for segment in key.split('.'):
                    options = properties(node)
                    self.assertIn(segment,options,key)
                    node = options[segment]

    def test_three_discovery_fixtures_guarded_deterministic_readonly(self):
        for name,language,bot in (('python','Python','coderabbit'),('typescript','TypeScript','greptile'),('greenfield',None,None)):
            with self.subTest(name=name):
                shutil.copytree(FIXTURES/name,self.root,dirs_exist_ok=True)
                before = support.tree_hashes(self.root)
                first = self.cli('discover.py','--json')
                second = self.cli('discover.py','--json')
                self.assertEqual(0,first.returncode,first.stderr)
                self.assertEqual(first.stdout,second.stdout)
                result = json.loads(first.stdout)
                self.assertEqual(before,support.tree_hashes(self.root))
                if language:
                    self.assertIn(language,result['languages'])
                    self.assertTrue(result['test_command'])
                    self.assertTrue(result['bots'][bot]['configs'])
                    self.assertEqual('github-actions',result['ci']['provider'])
                else:
                    self.assertTrue(result['greenfield'])
                    self.assertIsNone(result['test_command'])
                    self.assertIsNone(result['ci']['provider'])
                self.assertEqual('unknown',result['capabilities']['auth'])
                self.assertEqual('unknown',result['capabilities']['effective_models'])
                self.assertFalse(discover.discover(self.root,path=str(self.base/'empty-path'))['binaries']['codex'])
                shutil.rmtree(self.root)
                self.root.mkdir()

    def test_secrets_excluded_and_manifest_values_redacted(self):
        for path in ('.env','credentials.json','private.key','transcripts/raw.txt','node_modules/manifest.json'):
            target = self.root/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('never read this payload')
        token = 'sk-'+'A1b2'*8
        (self.root/'package.json').write_text(json.dumps({'scripts':{'test':'echo '+token}}))
        reads = []
        original = discover.config.read_bytes
        def capture(root,relative,**kwargs):
            reads.append(relative)
            return original(root,relative,**kwargs)
        before = support.tree_hashes(self.root)
        with mock.patch.object(discover.config,'read_bytes',side_effect=capture):
            result = discover.discover(self.root)
        self.assertIsNone(result['commands'][0]['declaration'])
        self.assertNotIn(token,json.dumps(result))
        self.assertFalse(any(p in reads for p in ('.env','credentials.json','private.key','transcripts/raw.txt','node_modules/manifest.json')))
        self.assertEqual(before,support.tree_hashes(self.root))

    def test_proposal_readonly_approval_binding_and_valid_config(self):
        before = support.tree_hashes(self.root)
        p = self.proposal()
        self.assertEqual(before,support.tree_hashes(self.root))
        self.assertEqual(20,len(p['answers']))
        self.assertFalse(p['config']['operations']['enabled'])
        self.assertNotIn('eval',p['config'])
        self.assertNotIn('max_parallel_workers',p['config']['budgets'])
        for sha,reference in (('', 'decision'),('0'*64,'decision'),(p['sha256'],'')):
            with self.assertRaises(setup.Error):
                setup.apply(self.root,p,sha,reference)
            self.assertEqual(before,support.tree_hashes(self.root))
        result = self.approve(p)
        self.assertEqual('applied',result['status'])
        discover.config.validate_file(self.root/discover.CONFIG,self.root)
        receipt = json.loads((self.root/discover.RECEIPT).read_text())
        self.assertEqual(p['sha256'],receipt['proposal_sha256'])
        self.assertEqual(20,len(receipt['answers']))
        self.assertFalse((self.root/'.software-factory/active.json').exists())

    def test_reonboard_preserves_existing_docs_config_and_confirmed_answers(self):
        self.crawl_fixture()
        (self.root/'ARCHITECTURE.md').write_text('# Existing architecture\nKeep these bytes.\n')
        p = self.proposal()
        answers = copy.deepcopy(p['answers'])
        answers[0] = {'id':1,'state':'confirmed','value':'Local approved intent','source':'owner-decision:scope'}
        p = setup.propose(self.root,answers)
        self.approve(p)
        before = support.tree_hashes(self.root)
        self.assertEqual('unchanged',self.approve(p)['status'])
        again = self.proposal()
        self.assertEqual([],again['changes'])
        self.assertEqual(answers,again['answers'])
        self.assertEqual(before,support.tree_hashes(self.root))
        self.assertEqual('# Existing architecture\nKeep these bytes.\n',(self.root/'ARCHITECTURE.md').read_text())
        with self.assertRaisesRegex(setup.Error,'immutable'):
            setup.propose(self.root,p['answers'][:-1]+[{**p['answers'][-1],'value':'changed'}])

    def test_grounded_document_drafts_and_existing_config_adoption(self):
        p = self.proposal()
        path = setup.HOME+'principles/product.md'
        text = '# Product draft\nDeliver one arithmetic behavior with a regression test.\n'
        p = setup.propose(self.root,draft_documents={path:text})
        self.assertEqual(text,p['files'][path])
        self.approve(p)
        (self.root/discover.RECEIPT).unlink()
        before = support.tree_hashes(self.root)
        adopted = self.proposal()
        self.assertEqual({},adopted['files'])
        self.approve(adopted)
        after = support.tree_hashes(self.root)
        for name,fingerprint in before.items():
            self.assertEqual(fingerprint,after[name])

    def test_stale_collision_partial_and_foreign_project_rejected(self):
        for mode in ('stale','collision','partial','foreign'):
            with self.subTest(mode=mode):
                p = self.proposal()
                if mode == 'stale':
                    (self.root/'README.md').write_text('new source')
                elif mode in ('collision','partial'):
                    target = self.root/next(iter(p['files']))
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text('preserve partial work')
                else:
                    p['root_identity'][1] += 1
                    p['sha256'] = discover.digest(discover.encoded({k:v for k,v in p.items() if k!='sha256'}))
                before = support.tree_hashes(self.root)
                with self.assertRaises(setup.Error):
                    self.approve(p)
                self.assertEqual(before,support.tree_hashes(self.root))
                shutil.rmtree(self.root)
                self.root.mkdir()

    def test_partial_publish_failure_preserves_bytes_without_receipt(self):
        p = self.proposal()
        original = setup.publish
        calls = []
        def fail_after_one(root,path,content,identity):
            if calls:
                raise OSError('injected publication failure')
            calls.append(path)
            original(root,path,content,identity)
        with mock.patch.object(setup,'publish',side_effect=fail_after_one), self.assertRaisesRegex(setup.Error,'incomplete'):
            self.approve(p)
        self.assertTrue((self.root/calls[0]).is_file())
        self.assertFalse((self.root/discover.RECEIPT).exists())
        with self.assertRaisesRegex(setup.Error,'partial'):
            self.approve(p)

    def test_symlink_fifo_and_tampered_output_fail_without_external_effects(self):
        outside = self.base/'outside'
        outside.mkdir()
        (self.root/'pyproject.toml').symlink_to(outside/'manifest.toml')
        with self.assertRaises(setup.Error):
            discover.discover(self.root)
        (self.root/'pyproject.toml').unlink()
        os.mkfifo(self.root/'pyproject.toml')
        with self.assertRaises(setup.Error):
            discover.discover(self.root)
        (self.root/'pyproject.toml').unlink()
        p = self.proposal()
        p['files']['../outside/escape.md'] = 'outside'
        p['sha256'] = discover.digest(discover.encoded({k:v for k,v in p.items() if k!='sha256'}))
        with self.assertRaises(setup.Error):
            self.approve(p)
        self.assertEqual([],list(outside.iterdir()))

    def test_bmad_preserved_unknown_capabilities_and_monitoring_not_enabled(self):
        self.crawl_fixture()
        manifest = self.root/'_bmad/_config/manifest.yaml'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('installation:\n  version: 6.12.0\n')
        before = manifest.read_bytes()
        result = discover.discover(self.root)
        self.assertEqual('6.12.0',result['bmad']['version'])
        self.assertEqual('unknown',result['bmad']['host_coverage'])
        self.assertEqual('unknown',result['capabilities']['monitoring'])
        p = self.proposal()
        self.approve(p)
        self.assertEqual(before,manifest.read_bytes())
        data = copy.deepcopy(p['config'])
        data['operations']['enabled'] = True
        with self.assertRaises((setup.Error,discover.config.ConfigError)):
            setup.validate_candidate(discover.Reader(self.root),{discover.CONFIG:json.dumps(data)},data)

    def test_actual_config_json_types_validated_for_new_and_preserved_bytes(self):
        p = self.proposal()
        actual = json.loads(p['files'][discover.CONFIG])
        actual['autonomy']['commits'] = 0
        p['files'][discover.CONFIG] = json.dumps(actual)
        p['sha256'] = discover.digest(discover.encoded({k:v for k,v in p.items() if k!='sha256'}))
        before = support.tree_hashes(self.root)
        with self.assertRaises(discover.config.ConfigError):
            self.approve(p)
        self.assertEqual(before,support.tree_hashes(self.root))
        p = self.proposal()
        self.approve(p)
        (self.root/discover.RECEIPT).unlink()
        adopt = self.proposal()
        actual = json.loads((self.root/discover.CONFIG).read_text())
        actual['autonomy']['commits'] = 0
        (self.root/discover.CONFIG).write_text(json.dumps(actual))
        with self.assertRaises(discover.config.ConfigError):
            self.approve(adopt)
        self.assertFalse((self.root/discover.RECEIPT).exists())

    def test_apply_root_swap_at_actual_publication_never_targets_replacement(self):
        p = self.proposal()
        real = setup.publish
        def replace(root,path,content,identity):
            self.root.rename(self.base/'approved-original')
            self.root.mkdir()
            real(root,path,content,identity)
        with mock.patch.object(setup,'publish',side_effect=replace), self.assertRaisesRegex(setup.Error,'incomplete'):
            self.approve(p)
        self.assertEqual([],list(self.root.iterdir()))
        self.assertEqual([],list((self.base/'approved-original').iterdir()))

    def test_replay_rejects_changed_source_and_directory_preserving_user_bytes(self):
        for change in ('file','inventory'):
            p = self.proposal()
            self.approve(p)
            if change == 'file':
                (self.root/'README.md').write_text('changed source')
            else:
                target = self.root/'.github/workflows/new.yml'
                target.parent.mkdir(parents=True)
                target.write_text('new workflow')
            before = support.tree_hashes(self.root)
            with self.assertRaisesRegex(setup.Error,'stale'):
                self.approve(p)
            self.assertEqual(before,support.tree_hashes(self.root))
            shutil.rmtree(self.root)
            self.root.mkdir()

    def test_mid_apply_inventory_change_and_final_receipt_race_fail_closed(self):
        for changed_path, at_receipt in (('.github/workflows/new.yml',False),('_bmad/new.md',False),('README.md',True)):
            p = self.proposal()
            real = setup.publish
            def change(root,path,content,identity,real=real,at_receipt=at_receipt,changed_path=changed_path):
                real(root,path,content,identity)
                if not at_receipt or path == discover.RECEIPT:
                    target = self.root/changed_path
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text('preserved concurrent input')
            with mock.patch.object(setup,'publish',side_effect=change), self.assertRaisesRegex(setup.Error,'incomplete'):
                self.approve(p)
            self.assertEqual('preserved concurrent input',(self.root/changed_path).read_text())
            if not at_receipt:
                self.assertFalse((self.root/discover.RECEIPT).exists())
            else:
                with self.assertRaisesRegex(setup.Error,'stale'):
                    self.approve(p)
            shutil.rmtree(self.root)
            self.root.mkdir()

    def test_preserved_enabled_monitoring_declaration_does_not_grant_access(self):
        p = self.proposal()
        self.approve(p)
        (self.root/discover.RECEIPT).unlink()
        data = discover.config.load(self.root/discover.CONFIG)
        policy = setup.HOME+'principles/risk.md'
        data['environments'] = {'local':{'kind':'local','expected_host':'local','shared_resources':[]}}
        data['operations'] = {'enabled':True,'authority_ref':policy,'until':'end of approved session','sources':[{'id':'health','environment':'local','kind':'health','locator':'local-status','read_scope':'read-only snapshot','data_policy_ref':policy,'trigger_refs':[policy],'dedup_keys':['source','condition']}]}
        (self.root/discover.CONFIG).write_bytes(discover.encoded(data))
        original = (self.root/discover.CONFIG).read_bytes()
        adopted = self.proposal()
        self.assertEqual('unknown',adopted['discovery']['capabilities']['monitoring'])
        self.approve(adopted)
        self.assertEqual(original,(self.root/discover.CONFIG).read_bytes())

    def test_custom_config_reuses_chosen_documents_without_competing_drafts(self):
        original = self.proposal()
        data = copy.deepcopy(original['config'])
        with self.assertRaises(discover.config.ConfigError):
            setup.propose(self.root,draft={**data,'documents':None})
        for name in data['documents']['principles'].values():
            path = self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('# Existing approved source\nPreserve these bytes.\n')
        data['documents']['conventions'] = data['documents']['principles']['conventions']
        for relative in (data['documents']['architecture'],data['tracker']['path'],'evals/actual-plan.json'):
            path = self.root/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('{}\n' if relative.endswith('.json') else '# Existing source\n')
        data['documents']['extra_context'] = ['evals/actual-plan.json']
        self.crawl_fixture()
        before = support.tree_hashes(self.root)
        proposal = setup.propose(self.root,draft=data)
        self.assertEqual({discover.CONFIG},set(proposal['files']))
        self.assertEqual(before,support.tree_hashes(self.root))
        self.approve(proposal)
        self.assertFalse((self.root/(setup.HOME+'CONVENTIONS.md')).exists())
        self.assertFalse((self.root/(setup.HOME+'evals-draft.json')).exists())

    def test_installed_templates_and_self_contained_setup_without_source_checkout(self):
        self.crawl_fixture()
        result = support.run_installer('install','--project',self.root,'--host','all','--skip-bmad',env=self.env)
        self.assertEqual(0,result.returncode,result.stderr)
        for prefix in ('.claude/skills','.agents/skills'):
            for name in ('PRINCIPLES.md','ARCHITECTURE.md','CONVENTIONS.md'):
                self.assertEqual((support.REPO/'templates'/name).read_bytes(),(self.root/prefix/'sf-help/templates'/name).read_bytes())
            before = support.tree_hashes(self.root)
            run = subprocess.run([sys.executable,str(self.root/prefix/'sf-help/scripts/setup.py'),'propose','--project',str(self.root)],cwd=self.base,env=self.env,capture_output=True,text=True,check=False)
            self.assertEqual(0,run.returncode,run.stderr)
            self.assertEqual(20,len(json.loads(run.stdout)['answers']))
            self.assertEqual(before,support.tree_hashes(self.root))

    def test_malformed_manifest_shapes_partial_bmad_and_unrecognized_layout(self):
        for package in ({'devDependencies':None,'scripts':[]},{'devDependencies':42,'scripts':False},{'packageManager':[]}):
            (self.root/'package.json').write_text(json.dumps(package))
            self.assertEqual([],discover.discover(self.root)['commands'])
        (self.root/'package.json').unlink()
        (self.root/'_bmad').mkdir()
        observation = discover.discover(self.root)
        self.assertTrue(observation['bmad']['tree_present'])
        self.assertEqual('preserve-and-observe',observation['bmad']['action'])
        self.assertFalse(observation['greenfield'])
        self.assertIn('unknown',observation['layout'])
        (self.root/'_bmad').rmdir()
        (self.root/'main.custom').write_text('unrecognized source')
        self.assertFalse(discover.discover(self.root)['greenfield'])
        with self.assertRaisesRegex(setup.Error,'sf-crawl'):
            self.proposal()

    def test_discovery_to_proposal_source_and_root_replacement_rejected(self):
        self.crawl_fixture()
        real = discover.discover
        def change_source(root):
            observed = real(root)
            (self.root/discover.CRAWL).write_text('changed source')
            return observed
        with mock.patch.object(discover,'discover',side_effect=change_source), self.assertRaisesRegex(setup.Error,'changed after discovery'):
            self.proposal()
        def change_root(root):
            observed = real(root)
            self.root.rename(self.base/'old-project')
            self.root.mkdir()
            return observed
        with mock.patch.object(discover,'discover',side_effect=change_root), self.assertRaisesRegex(setup.Error,'project changed'):
            self.proposal()

    def test_changed_source_mid_apply_never_publishes_receipt(self):
        p = self.proposal()
        real = setup.publish
        def change_source(root,path,content,identity):
            real(root,path,content,identity)
            (self.root/'README.md').write_text('concurrent user change')
        with mock.patch.object(setup,'publish',side_effect=change_source), self.assertRaisesRegex(setup.Error,'incomplete'):
            self.approve(p)
        self.assertFalse((self.root/discover.RECEIPT).exists())

    def test_scripted_forward_use_exercise_is_not_live_agent_evidence(self):
        p = self.proposal()
        self.approve(p)
        # Scripted consumer exercise: one behavior, failing proof, reviewed fix,
        # next independent local work; no publication/monitoring authority inferred.
        behavior = self.root/'behavior.py'
        behavior.write_text('def add(a, b): return a - b\n')
        (self.root/'test_behavior.py').write_text('import unittest\nfrom behavior import add\nclass TestAdd(unittest.TestCase):\n    def test_add(self): self.assertEqual(5, add(2, 3))\n')
        command = [sys.executable,'-m','unittest','test_behavior.py']
        failed = subprocess.run(command,cwd=self.root,env=self.env,capture_output=True,text=True,check=False)
        self.assertEqual(1,failed.returncode)
        behavior.write_text('def add(a, b): return a + b\n')
        passed = subprocess.run(command,cwd=self.root,env=self.env,capture_output=True,text=True,check=False)
        self.assertEqual(0,passed.returncode,passed.stderr)
        config = discover.config.load(self.root/discover.CONFIG)
        self.assertEqual('continue-independent',config['autonomy']['blocked_behavior'])
        self.assertFalse(config['autonomy']['deploy'])
        self.assertFalse(config['operations']['enabled'])
        self.assertEqual('epic-acceptance',config['checkpoints']['transitions'][0])
