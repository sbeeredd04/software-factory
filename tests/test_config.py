"""Full configuration validation and non-executing semantic contracts."""
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

config = support.helper('config')


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'project'
        shutil.copytree(support.REPO / 'examples/config', self.root)
        self.path = self.root / 'config.yaml'
        self.data = config.load(self.path)

    def check(self, data=None):
        return config.validate_data(self.data if data is None else data, self.root)

    def test_full_example_and_eval_compatibility(self):
        self.check()
        self.assertEqual(config.load(support.REPO / 'skills/sf-eval/examples/eval.config.example.json'), self.data['eval'])
        self.assertIsInstance(self.data['verification']['required_checks'], list)

    def test_existing_eval_golden_and_json_state_grades_are_preserved(self):
        for grade in (
            {'type':'golden', 'golden':'evals/goldens/out.txt', 'command':'echo approved-fixture'},
            {'type':'golden', 'golden':'evals/goldens/out.txt', 'path':'out/result.txt'},
            {'type':'state', 'path':'out/result.json', 'json':{'answer':42, 'nested.value':{'list':[True, None]}}},
        ):
            with self.subTest(grade=grade['type']):
                self.data['eval']['cases'][0]['grade'] = grade
                self.check()
                self.assertEqual(grade, self.data['eval']['cases'][0]['grade'])
        self.data['eval']['cases'][0]['grade'] = {'type':'golden', 'golden':'x'*2049}
        with self.assertRaises(config.ConfigError):
            self.check()
        self.data['eval']['cases'][0]['grade'] = {'type':'state', 'json':[]}
        with self.assertRaises(config.ConfigError):
            self.check()

    def test_semantic_rejections(self):
        cases = [
            ('native', lambda d: d['routing'].update(fallback='absent')),
            ('protected', lambda d: d['branches'].update(integration='main')),
            ('documents', lambda d: d['documents'].update(architecture='missing.md')),
            ('required bot', lambda d: d.update(review_bots={'review': {'enabled':False,'required':True,'config':'bot.json'}})),
        ]
        for reason, change in cases:
            data = copy.deepcopy(self.data)
            change(data)
            with self.subTest(reason=reason), self.assertRaisesRegex(config.ConfigError, reason):
                self.check(data)

    def test_parallel_owner_ceiling_is_optional_and_positive_when_present(self):
        self.data['budgets'].pop('max_parallel_workers')
        self.check()
        for ceiling in (0, -1, None, True, 65):
            with self.subTest(ceiling=ceiling), self.assertRaises(config.ConfigError):
                self.check({**self.data, 'budgets': {**self.data['budgets'], 'max_parallel_workers': ceiling}})
        self.data['budgets']['max_parallel_workers'] = 1
        self.check()

    def test_versions_and_syntax(self):
        for value in (99, '1', True, 1.0, None):
            with self.subTest(value=value), self.assertRaisesRegex(config.ConfigError,'version'):
                self.check({**self.data,'version':value})
        for text in ('a: &anchor 1', '{"a":1,"a":2}', '{"a":NaN}', '[' * 1000):
            with self.subTest(text=text[:20]), self.assertRaises(config.ConfigError):
                config.parse(text)

    def test_secret_and_bypass_no_value_leak(self):
        values = ['sk-' + 'A1b2' * 8, 'AKIA' + 'Z' * 16, 'aB7cD2eF9gH4iJ6kL0mN3pQ8rS5tU1vW', '--yolo=true', '--trust', '--sandbox=danger-full-access', 'bypassPermissions']
        for value in values:
            data = copy.deepcopy(self.data)
            data['project']['name'] = value
            with self.subTest(value=value[:3]), self.assertRaises(config.ConfigError) as caught:
                self.check(data)
            self.assertNotIn(value, str(caught.exception))

    def test_force_only_with_pinned_workspace_and_placeholders(self):
        self.data['agents']['external'] = {'kind':'external','description':'External configured agent','risk_tiers':[0], 'invoke':{'argv':['cursor-agent','--force','--workspace','{workspace}','{task_file}'],'cwd':'.','operation':'write'}}
        self.check()
        for token in ('{unknown}', '$' + '(touch marker)', 'prefix{workspace}'):
            self.data['agents']['external']['invoke']['argv'][-1] = token
            with self.assertRaises(config.ConfigError):
                self.check()

    def test_force_equals_and_normalized_authority_aliases(self):
        recipe = {'argv':['cursor-agent','--force=true'],'cwd':'.','operation':'write'}
        self.data['agents']['external'] = {'kind':'external','description':'Configured agent','risk_tiers':[0],'invoke':recipe}
        with self.assertRaisesRegex(config.ConfigError,'pinned'):
            self.check()
        recipe['argv'] += ['--workspace','{workspace}']
        self.check()
        recipe['argv'][0] = 'other-executable'
        with self.assertRaisesRegex(config.ConfigError,'pinned'):
            self.check()
        del self.data['agents']['external']
        for target in ('.', '.software-factory', './.software-factory/config.yaml','.software-factory//installation.json','./.software-factory/context/board/story.json'):
            self.data['extensions']['overlays'] = [{'id':'overlay','source':'PRODUCT.md','target':target,'base_sha256':'a'*64}]
            with self.subTest(target=target), self.assertRaisesRegex(config.ConfigError,'authority store'):
                self.check()
        self.data['board']['dir'] = './work/board'
        self.data['extensions']['overlays'][0]['target'] = 'work/board'
        with self.assertRaisesRegex(config.ConfigError,'authority store'):
            self.check()
        self.data['extensions']['overlays'][0]['target'] = 'work'
        with self.assertRaisesRegex(config.ConfigError,'authority store'):
            self.check()

    def test_paths_cwd_and_no_writes(self):
        before = support.tree_hashes(self.root)
        for cwd in (support.REPO, self.root.parent):
            result = support.run('config','validate','--config',self.path,cwd=cwd)
            self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual(before,support.tree_hashes(self.root))
        for value in ('../outside.md','/outside.md'):
            self.data['documents']['architecture'] = value
            with self.assertRaisesRegex(config.ConfigError,'contained'):
                self.check()

    def test_symlink_fifo_empty_and_path_only_mode(self):
        doc = self.root / 'ARCHITECTURE.md'
        doc.unlink()
        doc.symlink_to(self.root / 'PRODUCT.md')
        with self.assertRaises(config.ConfigError):
            self.check()
        doc.unlink()
        os.mkfifo(doc)
        with self.assertRaises(config.ConfigError):
            self.check()
        doc.unlink()
        doc.write_text('')
        with self.assertRaises(config.ConfigError):
            self.check()
        config.validate_data(self.data, self.root, check_paths=False)

    def test_leaf_and_ancestor_replacement_fail_without_reading_external_bytes(self):
        for ancestor in (False,True):
            with self.subTest(ancestor=ancestor):
                inside = self.root / ('ancestor' if ancestor else 'leaf')
                inside.mkdir()
                target = inside / 'doc.md'
                target.write_text('captured source')
                outside = self.root.parent / ('outside-ancestor' if ancestor else 'outside-leaf')
                outside.mkdir()
                (outside/'doc.md').write_text('external bytes must remain untouched')
                real_read = config.os.read
                swapped = False
                def replace(fd, count, real_read=real_read, ancestor=ancestor, inside=inside, target=target, outside=outside):
                    nonlocal swapped
                    content = real_read(fd,count)
                    if content and not swapped:
                        swapped = True
                        if ancestor:
                            inside.rename(inside.with_name(inside.name+'-old'))
                            inside.symlink_to(outside,target_is_directory=True)
                        else:
                            target.unlink()
                            target.symlink_to(outside/'doc.md')
                    return content
                with mock.patch.object(config.os,'read',side_effect=replace), self.assertRaises(config.ConfigError):
                    config.read_bytes(self.root, inside.name+'/doc.md')
                self.assertEqual('external bytes must remain untouched',(outside/'doc.md').read_text())

    def test_extensions_and_monitoring(self):
        self.data['extensions']['skills'] = [{'id':'local','source':'local-skills'}]
        self.check()
        self.data['extensions']['skills'][0]['source'] = '../escape'
        with self.assertRaises(config.ConfigError):
            self.check()
        self.data['extensions']['skills'] = []
        self.data['operations']['enabled'] = True
        with self.assertRaisesRegex(config.ConfigError,'authority'):
            self.check()

    def test_all_labeled_fixtures(self):
        for path in sorted((support.REPO/'tests/fixtures/config').glob('*.yaml')):
            with self.subTest(fixture=path.name):
                result = support.run('config','validate','--config',path)
                self.assertEqual(path.name.startswith('valid-'), result.returncode == 0, result.stderr)
                if result.returncode:
                    self.assertIn('config:',result.stderr)
