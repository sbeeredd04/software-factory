"""Registry/BMad observations, shipped dependency closure and behavioral contracts."""
import copy
import json
import shutil
import subprocess
import sys
from unittest import mock

import support
from test_overlays import MANIFEST, TARGET, OverlayCase, api, config, evolve, load


class RegistryTests(OverlayCase):
    def skill(self):
        binding = self.write('vendor/sample/SKILL.md', b'---\nname: sample\n---\nInspect a sample.\n')
        return {'id':'sample','source':binding['path'],'sha256':binding['sha256'],
                'upstream':'https://example.test/sample','revision':'1'*40,'license':'MIT',
                'provenance':self.write('evidence/license.md', b'Synthetic MIT provenance.\n'),
                'capabilities':['inspect'],'triggers':['sample request'],'phases':['review'],
                'permissions':[]}

    def test_complete_and_legacy_incomplete_metadata_never_adopts_or_connects(self):
        skill = self.skill()
        self.data['extensions']['skills'] = [skill, {'id':'pending','source':'vendor/missing.md'}]
        self.data['extensions']['mcp'] = [{'id':'pending-server','config':'mcp/server.json','enabled':True}]
        self.write_config()
        result = evolve.registry(self.root)
        self.assertEqual(['declared','incomplete'], [i['status'] for i in result['entries']['skills']])
        self.assertEqual('incomplete', result['entries']['mcp'][0]['status'])
        self.assertFalse(any(i['adopted'] or i['connected'] for entries in result['entries'].values() for i in entries))
        self.assertNotIn('Inspect a sample', json.dumps(result))
        self.assertFalse((self.root/'mcp/server.json').exists())

    def test_untrusted_mcp_request_keeps_auth_unknown_and_config_unread(self):
        secret_config = self.write('mcp/server.json', b'{"access_token":"synthetic private configuration"}')
        evidence = self.write('evidence/request.md', b'Untrusted candidate from a review comment; not consent.\n')
        consent = self.write('evidence/consent.md', b'Fixture owner permits metadata review only.\n')
        self.data['extensions']['mcp'] = [{'id':'sample-server','config':secret_config['path'],'enabled':True,
                                         'transport':'stdio','capabilities':['read'], 'auth_env':['SAMPLE_TOKEN'],
                                         'provenance':evidence,'consent':consent}]
        self.write_config()
        original = config.read_bytes
        def guard(root, relative, **kwargs):
            if str(relative) == secret_config['path']:
                self.fail('registry must not read MCP config to fill metadata')
            return original(root, relative, **kwargs)
        with mock.patch.object(config, 'read_bytes', side_effect=guard):
            result = evolve.registry(self.root)
        self.assertEqual('declared', result['entries']['mcp'][0]['status'])
        self.assertFalse(result['entries']['mcp'][0]['connected'])
        self.assertNotIn('private configuration', json.dumps(result))

    def test_unknown_license_permissions_and_empty_capabilities_block_adoption(self):
        for key, value in (('license','unknown'),('license','NOASSERTION'),('permissions',['unknown']),('capabilities',[])):
            with self.subTest(key=key, value=value):
                skill = self.skill()
                skill[key] = value
                self.data['extensions']['skills'] = [skill]
                self.write_config()
                self.assertEqual('incomplete', evolve.registry(self.root)['entries']['skills'][0]['status'])

    def test_reserved_duplicate_ids_credentials_and_changed_pin_refused(self):
        skill = self.skill()
        for transform in (
            lambda entry: entry.update(id='SF-CRAWL'),
            lambda entry: entry.update(sha256='0'*64),
            lambda entry: entry.update(source='../../escaped'),
            lambda entry: entry.update(source='/absolute'),
            lambda entry: entry.update(password='credential'),
        ):
            changed = copy.deepcopy(skill)
            transform(changed)
            self.data['extensions']['skills'] = [changed]
            self.write_config()
            with self.assertRaises((config.ConfigError,evolve.Error)):
                evolve.registry(self.root)
        self.data['extensions']['skills'] = [skill, copy.deepcopy(skill)]
        self.write_config()
        with self.assertRaises(config.ConfigError):
            evolve.registry(self.root)

    def test_decision_directory_alias_is_protected(self):
        self.manifest()
        self.data['autonomy']['standing_delegations'] = [{'source':TARGET,'sha256':'a'*64,'scope':'fixture'}]
        self.write(TARGET, b'Named governing decision')
        self.write_config()
        with self.assertRaises(config.ConfigError):
            evolve.registry(self.root)


class BmadTests(OverlayCase):
    def bmad(self):
        self.write('_bmad/_config/manifest.yaml', evolve.encoded({'installation':{'version':'6.12.0'},'modules':[],'ides':[]}))
        path = '.claude/skills/bmad-build/customize.toml'
        self.write(path, b'[workflow]\npersistent_facts = ["base"]\non_complete = ""\nimplementation_handoff = ""\n[[workflow.review_layers]]\nid = "check"\ninstruction = "base"\n')
        return path

    def test_shape_merge_matches_keyed_replacement_and_unkeyed_append(self):
        base = {'a':{'scalar':1,'list':['first'],'layers':[{'id':'one','instruction':'old','extra':'retained only if restated'}]}, 'unknown':'preserved'}
        changed = {'a':{'scalar':2,'list':['second'],'layers':[{'id':'one','instruction':'new'},{'id':'two','instruction':'added'}]}}
        result = evolve.merge_customization(base, changed)
        self.assertEqual('preserved', result['unknown'])
        self.assertEqual(2, result['a']['scalar'])
        self.assertEqual(['first','second'], result['a']['list'])
        self.assertEqual(changed['a']['layers'], result['a']['layers'])
        self.assertEqual([{'id':'one'},{'code':'two'}], evolve.merge_customization([{'id':'one'}],[{'code':'two'}]))

    def test_installed_fields_authority_unsupported_knob_and_unknown_version(self):
        path = self.bmad()
        self.assertEqual('unsupported', evolve.bmad_inspect(self.root,path,{'workflow':{'lenses':[]}})['status'])
        result = evolve.bmad_inspect(self.root,path,{'workflow':{'persistent_facts':['local']}})
        self.assertEqual('needs-host-review', result['status'])
        self.assertFalse(result['dispatch_allowed'])
        self.assertFalse(result['resolver_executed'])
        self.write('_bmad/_config/manifest.yaml', evolve.encoded({'installation':{'version':'7.0.0'},'modules':[],'ides':[]}))
        self.assertEqual('unsupported', evolve.bmad_inspect(self.root,path)['status'])

    def test_recursive_effective_personal_route_refused_without_rewriting(self):
        path = self.bmad()
        self.write('_bmad/custom/bmad-build.toml', b'[workflow]\npersistent_facts=["team"]\n[custom]\nunknown="preserved"\n')
        self.write('_bmad/custom/bmad-build.user.toml', b'[workflow]\non_complete="Invoke software-factory again"\n')
        before = support.tree_hashes(self.root)
        result = evolve.bmad_inspect(self.root,path,{'workflow':{'on_complete':'return output'}})
        self.assertEqual('recursive', result['status'])
        self.assertFalse(result['dispatch_allowed'])
        self.assertEqual(before, support.tree_hashes(self.root))


class PackagingTests(OverlayCase):
    def run_helper(self, helper, *args):
        return subprocess.run([sys.executable,str(helper),*args], env=self.env,
                              cwd=self.base,capture_output=True,text=True,check=False)

    def test_all_installed_and_native_contexts_run_without_source_checkout(self):
        value = self.manifest()
        # A complete movable release source rather than ancestors in a checkout.
        source = self.base/'release-source'
        shutil.copytree(support.REPO, source, ignore=shutil.ignore_patterns('.git','.software-factory','__pycache__','dist'))
        installer = source/'install.py'
        run = subprocess.run([sys.executable,str(installer),'install','--project',str(self.root),'--host','all','--skip-bmad'],env=self.env,capture_output=True,text=True,check=False)
        self.assertEqual(0, run.returncode, run.stderr)
        bundles = self.base/'bundles'
        run = subprocess.run([sys.executable,str(source/'scripts/distribution.py'),'--host','all','--out',str(bundles)],env=self.env,capture_output=True,text=True,check=False)
        self.assertEqual(0, run.returncode, run.stderr)
        shutil.rmtree(source)
        helpers = [self.root/p/'sf-evolve/scripts/evolve.py' for p in ('.claude/skills','.agents/skills')]
        helpers += [bundles/host/'plugins/software-factory/skills/sf-evolve/scripts/evolve.py' for host in ('claude-code','cursor','codex')]
        for helper in helpers:
            with self.subTest(helper=helper):
                result = self.run_helper(helper,'inspect','--root',str(self.root),'--manifest',MANIFEST,'--base','evidence/base.md')
                self.assertEqual(0,result.returncode,result.stderr)
                self.assertEqual(value['subject_sha256'],json.loads(result.stdout)['subject_sha256'])
                schema = helper.parent.parent/'schemas/overlay.schema.json'
                self.assertEqual((support.REPO/'schemas/overlay.schema.json').read_bytes(),schema.read_bytes())
                self.assertIn('SOURCE_LAYOUT = False',helper.read_text())
                schema.unlink()
                # A hostile source-like consumer ancestor cannot replace the schema.
                self.write('schemas/overlay.schema.json',b'{}')
                result = self.run_helper(helper,'inspect','--root',str(self.root),'--manifest',MANIFEST,'--base','evidence/base.md')
                self.assertNotEqual(0,result.returncode)
                self.assertFalse(result.stdout)

    def test_bmad_parser_dependency_projects_in_every_bundle(self):
        dist = load(support.REPO/'scripts/distribution.py', 'sf_evolve_dist')
        for host in api.REGISTERED_HOSTS:
            files = dist.bundle_files(api,host)
            self.assertEqual((support.REPO/'scripts/bmad_install.py').read_bytes(),
                             files['plugins/software-factory/skills/sf-evolve/scripts/bmad_install.py'])

    def test_bounded_artifacts_duplicate_json_and_large_proposal_roundtrip(self):
        with self.assertRaises(evolve.Error):
            evolve.agents.parse_artifact(b'{"a":1,"a":2}')
        value = {'diff':'x'*20000, 'sources':{'a'*200:'0'*64}}
        self.assertEqual(value,evolve.agents.parse_artifact(evolve.artifact(value)))
        with self.assertRaises(evolve.Error):
            evolve.artifact({'diff':'x'*(config.MAX_BYTES+1)})
