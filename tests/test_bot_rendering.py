"""Approved rule projections preserve user bytes and recover contested writes."""
import copy
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
from test_agents import fixture, helper, save

B = helper('render_bots')


class BotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()/'consumer'
        self.data = fixture(self.root,True)
        for key,path in self.data['documents']['principles'].items():
            (self.root/path).write_text('Rule marker '+key+'\n')

    def plan(self,bots=None):
        return B.plan(self.root,list(B.TARGETS) if bots is None else bots,'decision:principles-approved')

    def apply(self,proposal):
        return B.apply(self.root,proposal,proposal['sha256'],'decision:reviewed-target-diff')

    def test_plan_zero_writes_four_sources_and_selected_only(self):
        before = support.tree_hashes(self.root)
        plan = self.plan(['copilot'])
        self.assertEqual(before,support.tree_hashes(self.root))
        self.assertEqual({'.github/copilot-instructions.md'},set(plan['files']))
        self.assertEqual(4,len(plan['principles']))
        for key in ('product','conventions','risk','evals'):
            self.assertIn('Rule marker '+key,plan['files']['.github/copilot-instructions.md'])
        self.assertEqual('not_applicable',self.plan([])['status'])
        self.assertEqual(before,support.tree_hashes(self.root))

    def test_all_four_formats_provenance_and_idempotent_apply(self):
        proposal = self.plan()
        result = self.apply(proposal)
        self.assertEqual('applied',result['status'])
        self.assertFalse(self.plan()['proposals'])
        for path in ('.greptile/rules.md','.coderabbit.yaml','.cursor/BUGBOT.md','.github/copilot-instructions.md'):
            raw = (self.root/path).read_text()
            for key in ('product','conventions','risk','evals'):
                self.assertIn('Rule marker '+key,raw)
            for sha in proposal['principles'].values():
                self.assertIn(sha,raw)
        self.assertIn('path_instructions:',(self.root/'.coderabbit.yaml').read_text())
        self.assertIn('version: 1',(self.root/'.cursor/config/bugbot.yaml').read_text())
        self.assertEqual([],json.loads((self.root/'.greptile/config.json').read_text())['autoReview'])
        before = support.tree_hashes(self.root)
        self.assertEqual('unchanged',self.apply(self.plan())['status'])
        self.assertEqual(before,support.tree_hashes(self.root))

    def test_user_markdown_and_complex_structured_config_preserved(self):
        examples = {'.cursor/BUGBOT.md':b'User text\r\nKeep this exactly.\r\n',
                    '.coderabbit.yaml':b'tone_instructions: "User tone"\r\nreviews:\r\n  path_instructions:\r\n    - path: custom/**\r\n      instructions: user rule\r\n',
                    '.greptile/config.json':b'{ "customRules": {"nested": [1, 2]}, "instructions": "keep" }\n'}
        for path,raw in examples.items():
            target = self.root/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
        proposal = self.plan()
        self.assertIn('.coderabbit.yaml',proposal['proposals'])
        self.assertIn('.greptile/config.json',proposal['proposals'])
        self.assertIn('Rule marker',proposal['proposals']['.greptile/config.json']['diff'])
        self.apply(proposal)
        for path in ('.coderabbit.yaml','.greptile/config.json'):
            self.assertEqual(examples[path],(self.root/path).read_bytes())
        self.assertTrue((self.root/'.cursor/BUGBOT.md').read_bytes().startswith(examples['.cursor/BUGBOT.md']))

    def test_changed_principles_update_only_receipted_section(self):
        self.apply(self.plan(['copilot']))
        target = self.root/'.github/copilot-instructions.md'
        old = target.read_bytes()
        target.write_bytes(b'User prefix\r\n'+old+b'User suffix\r\n')
        (self.root/'PRODUCT.md').write_text('New approved product rule\n')
        self.apply(self.plan(['copilot']))
        self.assertTrue(target.read_bytes().startswith(b'User prefix\r\n'))
        self.assertTrue(target.read_bytes().endswith(b'User suffix\r\n'))
        self.assertIn('New approved product rule',target.read_text())

    def test_tampered_section_or_duplicate_markers_proposal_only(self):
        self.apply(self.plan(['copilot']))
        target = self.root/'.github/copilot-instructions.md'
        for suffix in ('user edit inside',B.START):
            raw = target.read_text().replace('Rule marker product',suffix)
            target.write_text(raw)
            proposal = self.plan(['copilot'])
            self.assertFalse(proposal['files'])
            self.assertIn('.github/copilot-instructions.md',proposal['proposals'])
            self.assertEqual('proposal-only',self.apply(proposal)['status'])
            self.assertEqual(raw,target.read_text())

    def test_owned_yaml_with_new_unmanaged_keys_is_proposal_only(self):
        self.apply(self.plan(['coderabbit','bugbot']))
        targets = {'.coderabbit.yaml':'reviews:\n  tone_instructions: User tone\n',
                   '.cursor/config/bugbot.yaml':'version: 1\n'}
        originals = {}
        for path,prefix in targets.items():
            target = self.root/path
            originals[path] = prefix.encode()+target.read_bytes()
            target.write_bytes(originals[path])
        (self.root/'PRODUCT.md').write_text('Changed approved product principle\n')
        proposal = self.plan(['coderabbit','bugbot'])
        for path in targets:
            self.assertNotIn(path,proposal['files'])
            self.assertIn('unmanaged YAML',proposal['proposals'][path]['reason'])
        self.apply(proposal)
        for path,raw in originals.items():
            self.assertEqual(raw,(self.root/path).read_bytes())

    def test_missing_empty_unsafe_or_unapproved_principles_refuse(self):
        for value in ('', 'sf-setup-reuse/1'):
            with self.assertRaises(ValueError):
                B.plan(self.root,['copilot'],value)
        target = self.root/'PRODUCT.md'
        for raw in ('',B.START):
            target.write_text(raw)
            with self.assertRaises(ValueError):
                self.plan()
        target.unlink()
        target.symlink_to(self.root/'RISK.md')
        with self.assertRaises(ValueError):
            self.plan()

    def test_stale_digest_forged_paths_and_source_mutation_write_nothing(self):
        proposal = self.plan(['copilot'])
        before = support.tree_hashes(self.root)
        for forged in (dict(proposal,files={'arbitrary.txt':'bad'}),dict(proposal,sha256='0'*64)):
            with self.assertRaises(ValueError):
                self.apply(forged)
            self.assertEqual(before,support.tree_hashes(self.root))
        (self.root/'PRODUCT.md').write_text('changed')
        before = support.tree_hashes(self.root)
        with self.assertRaises(ValueError):
            self.apply(proposal)
        self.assertEqual(before,support.tree_hashes(self.root))

    def test_partial_failure_rolls_back_independent_targets_retains_recovery(self):
        proposal = self.plan(['copilot','bugbot'])
        helper = B.lifecycle()
        publish = helper.publish
        count = 0
        def fail_second(*args,**kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected failure')
            return publish(*args,**kwargs)
        with mock.patch.object(B,'lifecycle',return_value=helper),mock.patch.object(helper,'publish',side_effect=fail_second), self.assertRaisesRegex(B.Error,'recovery copies'):
            self.apply(proposal)
        self.assertFalse((self.root/'.cursor/BUGBOT.md').exists())
        self.assertFalse((self.root/B.RECEIPT).exists())
        self.assertTrue(list((self.root/'.software-factory/backups').glob('*/*.original')))

    def test_final_component_race_keeps_new_user_entry(self):
        target = self.root/'.github/copilot-instructions.md'
        target.parent.mkdir()
        target.write_text('Original user rules\n')
        proposal = self.plan(['copilot'])
        helper = B.lifecycle()
        publish = helper.publish
        def concurrent(fd,name,content,**kwargs):
            target.write_text('Late user edit\n')
            return publish(fd,name,content,**kwargs)
        with mock.patch.object(B,'lifecycle',return_value=helper),mock.patch.object(helper,'publish',side_effect=concurrent), self.assertRaises(B.Error):
            self.apply(proposal)
        self.assertEqual('Late user edit\n',target.read_text())
        self.assertFalse((self.root/B.RECEIPT).exists())

    def test_rollback_preserves_contested_target_and_restores_independent_target(self):
        proposal = self.plan(['bugbot','copilot'])
        helper = B.lifecycle()
        publish = helper.publish
        count = 0
        contested = self.root/'.cursor/config/bugbot.yaml'
        def fail_third(*args,**kwargs):
            nonlocal count
            count += 1
            if count == 3:
                contested.write_text('Late user configuration\n')
                raise OSError('injected failure after concurrent edit')
            return publish(*args,**kwargs)
        with mock.patch.object(B,'lifecycle',return_value=helper),mock.patch.object(helper,'publish',side_effect=fail_third), self.assertRaisesRegex(B.Error,'contested paths: .cursor/config/bugbot.yaml'):
            self.apply(proposal)
        self.assertEqual('Late user configuration\n',contested.read_text())
        self.assertFalse((self.root/'.cursor/BUGBOT.md').exists())
        self.assertFalse((self.root/'.github/copilot-instructions.md').exists())
        self.assertFalse((self.root/B.RECEIPT).exists())

    def test_symlink_ancestor_swap_does_not_write_external(self):
        target = self.root/'.github'
        target.mkdir()
        external = self.root.parent/'outside'
        external.mkdir()
        proposal = self.plan(['copilot'])
        helper = B.lifecycle()
        publish = helper.publish
        def swapped(fd,name,content,**kwargs):
            target.rename(self.root/'.github-old')
            target.symlink_to(external,target_is_directory=True)
            return publish(fd,name,content,**kwargs)
        with mock.patch.object(B,'lifecycle',return_value=helper),mock.patch.object(helper,'publish',side_effect=swapped), self.assertRaises(B.Error):
            self.apply(proposal)
        self.assertEqual([],list(external.iterdir()))

    def test_fifo_and_output_symlink_refused_without_mutation(self):
        target = self.root/'.github/copilot-instructions.md'
        target.parent.mkdir()
        os.mkfifo(target)
        with self.assertRaises(ValueError):
            self.plan(['copilot'])
        target.unlink()
        target.symlink_to(self.root/'PRODUCT.md')
        with self.assertRaises(ValueError):
            self.plan(['copilot'])

    def test_config_disabled_bot_refuses_selected_write(self):
        self.data['review_bots']['copilot']['enabled'] = False
        save(self.root,self.data)
        with self.assertRaises(B.Error):
            self.plan(['copilot'])

    def test_exact_approval_shape_and_setup_reuse_not_authority(self):
        proposal = self.plan(['copilot'])
        (self.root/'.software-factory/setup-receipt.json').write_text(json.dumps({'schema':'sf-setup-reuse/1'}))
        with self.assertRaises(ValueError):
            B.apply(self.root,proposal,'0'*64,'decision:real')
        with self.assertRaises(ValueError):
            B.apply(self.root,proposal,proposal['sha256'],'')
        tampered = copy.deepcopy(proposal)
        tampered['principles_ref'] = 'sf-setup-reuse/1'
        with self.assertRaises(ValueError):
            self.apply(tampered)

    def test_publication_dependency_is_byte_bound_and_capture_is_executed(self):
        source = support.REPO/'scripts/install_lifecycle.py'
        raw = source.read_bytes()
        self.assertEqual(B.LIFECYCLE_SHA256,B.D.digest(raw))
        with mock.patch.object(B.agents.config,'read_bytes',return_value=b'raise AssertionError("untrusted dependency")'),self.assertRaisesRegex(B.Error,'dependency digest mismatch'):
            B.lifecycle()
        # The path is not reopened by an import loader after the bounded capture.
        with mock.patch.object(B.agents.config,'read_bytes',return_value=raw),mock.patch.object(B.agents,'module',side_effect=AssertionError('reopened path')):
            self.assertTrue(callable(B.lifecycle().publish))

    def test_actual_cli_large_rules_prefix_and_long_source_path_roundtrip(self):
        env,guard,binary = support.guard_env()
        self.addCleanup(shutil.rmtree,binary,ignore_errors=True)
        for mode in ('large-rules','long-prefix','long-path'):
            root = Path(self.temp.name)/mode
            data = fixture(root,True)
            target = root/'.github/copilot-instructions.md'
            prefix = b''
            if mode == 'large-rules':
                for path in data['documents']['principles'].values():
                    (root/path).write_text('x'*4000+'\n')
            elif mode == 'long-prefix':
                target.parent.mkdir()
                prefix = b'User rules '+b'x'*20000+b'\r\n'
                target.write_bytes(prefix)
            else:
                path = 'principles/'+('nested-source-'*12)+'/product.md'
                self.assertGreater(len(path),128)
                (root/path).parent.mkdir(parents=True)
                (root/'PRODUCT.md').rename(root/path)
                data['documents']['principles']['product'] = path
                save(root,data)
            command = [sys.executable,'-I','-B',str(Path(B.__file__)),'--project',str(root)]
            prepared = subprocess.run(command+['plan','--bots','copilot','--principles-ref','decision:approved'],env=env,capture_output=True,text=True,check=False)
            self.assertEqual(0,prepared.returncode,prepared.stderr)
            proposal = json.loads(prepared.stdout)
            artifact = Path(self.temp.name)/(mode+'.json')
            artifact.write_text(prepared.stdout)
            applied = subprocess.run(command+['apply','--proposal',str(artifact),'--approved-sha',proposal['sha256'],'--decision','decision:reviewed'],env=env,capture_output=True,text=True,check=False)
            self.assertEqual(0,applied.returncode,applied.stderr)
            self.assertTrue(target.read_bytes().startswith(prefix))
            again = subprocess.run(command+['plan','--bots','copilot','--principles-ref','decision:approved'],env=env,capture_output=True,text=True,check=False)
            self.assertEqual(0,again.returncode,again.stderr)
            self.assertEqual({},json.loads(again.stdout)['files'])
        self.assertFalse(guard.exists())

    def test_oversized_encoded_proposal_refuses_before_any_write(self):
        target = self.root/'.github/copilot-instructions.md'
        target.parent.mkdir()
        target.write_text('x'*(B.agents.config.MAX_BYTES-400))
        before = support.tree_hashes(self.root)
        with self.assertRaisesRegex(B.Error,'proposal exceeds 1MiB artifact budget'):
            self.plan(['copilot'])
        self.assertEqual(before,support.tree_hashes(self.root))

    def test_plan_refuses_preserved_text_outside_artifact_contract(self):
        target = self.root/'.github/copilot-instructions.md'
        target.parent.mkdir()
        target.write_bytes(b'User prefix with a NUL: \x00\n')
        before = support.tree_hashes(self.root)
        with self.assertRaisesRegex(B.Error,'unsupported control'):
            self.plan(['copilot'])
        self.assertEqual(before,support.tree_hashes(self.root))
