"""Evidence-bound overlays use the existing installer transaction and recovery."""
import copy
import dataclasses
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


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api = load(support.REPO / 'install.py', 'sf_overlay_install')
evolve = load(support.REPO / 'skills/sf-evolve/scripts/evolve.py', 'sf_overlay_evolve')
config = evolve.config
TARGET = '.agents/skills/sf-crawl/references/artifact.md'
MANIFEST = '.software-factory/overlays/lesson/manifest.json'
PAYLOAD = '.software-factory/overlays/lesson/payload.md'


class OverlayCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'consumer'
        shutil.copytree(support.REPO / 'examples/config', self.root)
        self.data = json.loads((self.root / 'config.yaml').read_text())
        (self.root / 'config.yaml').unlink()
        self.data['project']['root'] = '..'
        self.data.pop('eval', None)
        self.write_config()
        self.env, self.guard, stubs = support.guard_env()
        self.addCleanup(shutil.rmtree, stubs, ignore_errors=True)
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'
        self.addCleanup(lambda: self.assertFalse(self.guard.exists(), 'agent CLI guard invoked'))

    def write(self, path, raw):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        return {'path':path, 'sha256':evolve.digest(raw)}

    def write_config(self):
        self.write('.software-factory/config.yaml', evolve.encoded(self.data))

    def manifest(self, target=TARGET, mode='append'):
        base = next(a.content for a in api.project_shared_skills(['codex']) if a.path == target)
        self.write('evidence/base.md', base)
        value = {'version':1, 'id':'lesson', 'target':target, 'base_sha256':evolve.digest(base),
                 'mode':mode, 'payload':self.write(PAYLOAD, b'\nReviewed local regression lesson.\n'),
                 'evidence':[self.write('evidence/failure.txt', b'Observed fixture failure, source revision recorded.\n')],
                 'author':'implementer', 'risk':'routine'}
        self.bind(value)
        return value

    def bind(self, value):
        value['subject_sha256'] = evolve.subject(value)
        subject = value['subject_sha256']
        review = {'subject_sha256':subject, 'by':'independent-reviewer', 'verdict':'approved'}
        value['review'] = {**review, 'artifact':self.write('evidence/review.json', evolve.encoded(review))}
        for kind in ('regression','canary'):
            receipt = {'subject_sha256':subject, 'result':'pass', 'cases':['failure scenario','retained behavior']}
            value[kind] = {'subject_sha256':subject, 'result':'pass', 'artifact':self.write('evidence/'+kind+'.json', evolve.encoded(receipt))}
        value['approval'] = {'subject_sha256':subject, 'by':'project-owner', 'kind':'standing-go',
                             'decision':self.write('evidence/decision.md', b'Fixture standing GO for reviewed routine local improvements.\n')}
        self.register(value)

    def register(self, value):
        binding = self.write(MANIFEST, evolve.encoded(value))
        self.data['extensions']['overlays'] = [{key:value[key] for key in ('id','target','base_sha256')} | {'source':MANIFEST, 'manifest_sha256':binding['sha256']}]
        self.write_config()

    def plan(self):
        return api.build_plan(self.root, ['codex'], 'skills-only', set())

    def apply(self):
        plan, conflicts, previous = self.plan()
        self.assertEqual([], conflicts)
        api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        return plan

    def cli(self, *args):
        return support.run_installer(*args, env=self.env)


class OverlayTests(OverlayCase):
    def test_schema_fixture_and_exact_composition(self):
        value = self.manifest()
        config.validate_schema(value, evolve.overlay_schema())
        config.validate_schema(evolve.agents.read_json(support.REPO/'tests/fixtures/overlays/manifest.json'), evolve.overlay_schema())
        manifest, payload = evolve.load_overlay(self.root, MANIFEST)
        base = (self.root / 'evidence/base.md').read_bytes()
        self.assertEqual(base + payload, evolve.plan_overlay(base, manifest, payload))
        self.assertEqual('proposed', evolve.inspect_overlay(self.root, MANIFEST, 'evidence/base.md')['status'])

    def test_reinstall_once_uninstall_preserves_overlay_sources_and_metadata(self):
        value = self.manifest()
        self.apply()
        expected = (self.root/'evidence/base.md').read_bytes() + (self.root/PAYLOAD).read_bytes()
        self.assertEqual(expected, (self.root/TARGET).read_bytes())
        plan, conflicts, _ = self.plan()
        self.assertFalse(conflicts)
        self.assertTrue(all(item.status == 'noop' for item in plan))
        ownership = json.loads((self.root/api.MANIFEST_REL).read_text())
        self.assertEqual(evolve.digest(expected), next(e['sha256'] for e in ownership['files'] if e['path'] == TARGET))
        self.assertEqual(value, json.loads((self.root/MANIFEST).read_text()))
        result = self.cli('uninstall','--project',self.root,'--host','codex')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.root/TARGET).exists())
        self.assertTrue((self.root/MANIFEST).exists())
        self.assertTrue((self.root/PAYLOAD).exists())
        self.assertTrue((self.root/'.software-factory/config.yaml').exists())

    def test_base_drift_proposal_and_installer_conflict_preserve_bytes(self):
        value = self.manifest()
        self.apply()
        value['base_sha256'] = '0'*64
        self.bind(value)
        before = support.tree_hashes(self.root)
        proposal = evolve.inspect_overlay(self.root, MANIFEST, 'evidence/base.md')
        self.assertEqual('conflict', proposal['status'])
        self.assertTrue(proposal['diff'])
        self.assertFalse(proposal['applied'])
        with self.assertRaises(api.InstallError):
            self.plan()
        self.assertEqual(before, support.tree_hashes(self.root))

    def test_edited_target_cannot_use_allow_overwrite(self):
        self.manifest()
        self.apply()
        self.write(TARGET, b'user edit\n')
        before = support.tree_hashes(self.root)
        _, conflicts, _ = api.build_plan(self.root, ['codex'], 'skills-only', {TARGET})
        self.assertTrue(any('unsupported' in c for c in conflicts))
        self.assertEqual(before, support.tree_hashes(self.root))

    def test_replacement_preserves_host_frontmatter(self):
        target = '.agents/skills/sf-crawl/SKILL.md'
        value = self.manifest(target, 'replace')
        base = (self.root/'evidence/base.md').read_bytes()
        for replacement in (base.replace(b'name: sf-crawl', b'name: changed'), b'---\nallowed-tools: all\n---\nbody'):
            value['payload'] = self.write(PAYLOAD, replacement)
            self.bind(value)
            with self.assertRaises(api.InstallError):
                self.plan()
        value['payload'] = self.write(PAYLOAD, base+b'\nReviewed body.\n')
        self.bind(value)
        self.apply()
        self.assertEqual(base+b'\nReviewed body.\n', (self.root/target).read_bytes())

    def test_manifest_schema_digest_proof_independence_and_material_refusals(self):
        value = self.manifest()
        for edit in (
            lambda m: m.update(subject_sha256='0'*64),
            lambda m: m['review'].update(by='implementer'),
            lambda m: m['canary'].update(result='fail'),
            lambda m: m['approval'].update(subject_sha256='0'*64),
            lambda m: m.update(unrecognized=True),
        ):
            changed = copy.deepcopy(value)
            edit(changed)
            self.register(changed)
            with self.assertRaises((api.InstallError, config.ConfigError, evolve.Error)):
                self.plan()
        value['risk'] = 'material'
        self.bind(value)
        with self.assertRaises(api.InstallError):
            self.plan()
        value['approval']['kind'] = 'human'
        self.register(value)
        self.assertFalse(self.plan()[1])

    def test_proof_receipt_cannot_claim_different_result_or_subject(self):
        value = self.manifest()
        value['canary']['artifact'] = self.write('evidence/canary.json', evolve.encoded({'result':'fail','subject_sha256':value['subject_sha256']}))
        self.register(value)
        with self.assertRaises(api.InstallError):
            self.plan()

    def test_missing_changed_payload_manifest_or_evidence_fails_without_writes(self):
        for path in (PAYLOAD, MANIFEST, 'evidence/failure.txt', 'evidence/decision.md'):
            with self.subTest(path=path):
                self.manifest()
                self.write(path, b'changed')
                before = support.tree_hashes(self.root)
                with self.assertRaises(api.InstallError):
                    self.plan()
                self.assertEqual(before, support.tree_hashes(self.root))

    def test_paths_symlink_fifo_oversize_duplicate_and_governing_alias(self):
        for path in ('../../outside', '/outside', '.agents/skills/sf-crawl/scripts/crawl.py', '.codex/hooks.json', '_bmad/custom/a.toml', '.agents/skills/software-factory/SKILL.md'):
            with self.subTest(path=path), self.assertRaises(evolve.Error):
                evolve.safe_target(path)
        value = self.manifest()
        self.data['documents']['principles']['risk'] = TARGET
        self.write(TARGET, b'governing risk document')
        self.write_config()
        with self.assertRaises(api.InstallError):
            self.plan()
        self.data['documents']['principles']['risk'] = 'RISK.md'
        self.register(value)
        self.data['extensions']['overlays'].append(copy.deepcopy(self.data['extensions']['overlays'][0]))
        self.write_config()
        with self.assertRaises(api.InstallError):
            self.plan()
        self.register(value)
        (self.root/PAYLOAD).unlink()
        (self.root/PAYLOAD).symlink_to(self.root/'RISK.md')
        with self.assertRaises(api.InstallError):
            self.plan()
        (self.root/PAYLOAD).unlink()
        os.mkfifo(self.root/PAYLOAD)
        with self.assertRaises(api.InstallError):
            self.plan()
        (self.root/PAYLOAD).unlink()
        self.write(PAYLOAD, b'a'*(config.MAX_BYTES+1))
        with self.assertRaises(api.InstallError):
            self.plan()

    def test_config_source_change_between_plan_and_lock_is_refused(self):
        self.manifest()
        plan, _, previous = self.plan()
        self.write(PAYLOAD, b'late payload')
        with self.assertRaises(api.InstallError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertFalse((self.root/TARGET).exists())

    def test_cli_validation_and_proposal_are_read_only(self):
        self.manifest()
        before = support.tree_hashes(self.root)
        command = [sys.executable, str(support.REPO/'skills/sf-evolve/scripts/evolve.py'),
                   'propose','--root',str(self.root),'--manifest',MANIFEST,'--base','evidence/base.md']
        run = subprocess.run(command, env=self.env, capture_output=True, check=False)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual('proposed', json.loads(run.stdout)['status'])
        self.assertEqual(before, support.tree_hashes(self.root))


class OverlayPublicationTests(OverlayCase):
    def changed_plan(self):
        self.manifest()
        self.apply()
        value = self.manifest()
        value['payload'] = self.write(PAYLOAD, b'\nNext reviewed lesson.\n')
        self.bind(value)
        return self.plan()

    def test_late_user_edit_before_capture_is_retained(self):
        plan, _, previous = self.changed_plan()
        lifecycle = api.lifecycle_api()
        original = lifecycle.publish
        def race(fd, name, content, **kw):
            if kw['relative'] == TARGET and content == next(p.after for p in plan if p.action.path == TARGET):
                (self.root/TARGET).write_bytes(b'late user edit')
            return original(fd, name, content, **kw)
        with mock.patch.object(api, 'lifecycle_api', return_value=lifecycle), mock.patch.object(lifecycle, 'publish', side_effect=race), self.assertRaises(OSError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertEqual(b'late user edit', (self.root/TARGET).read_bytes())
        self.assertEqual(previous, json.loads((self.root/api.MANIFEST_REL).read_text()))

    def test_exclusive_link_retains_replacement_and_captured_original(self):
        plan, _, previous = self.changed_plan()
        original_link = os.link
        raced = False
        def race(source, target, **kw):
            nonlocal raced
            if (target == Path(TARGET).name and str(source).endswith('.new') and not raced
                    and os.fstat(kw['dst_dir_fd']).st_ino == (self.root/TARGET).parent.stat().st_ino):
                raced = True
                (self.root/TARGET).write_bytes(b'concurrent replacement')
            return original_link(source, target, **kw)
        with mock.patch.object(os, 'link', side_effect=race), self.assertRaises(OSError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertTrue(raced)
        self.assertEqual(b'concurrent replacement', (self.root/TARGET).read_bytes())
        originals = list((self.root/api.BACKUPS_REL).rglob('*.original'))
        self.assertTrue(any(p.read_bytes() == next(i.before for i in plan if i.action.path == TARGET) for p in originals))

    def test_ancestor_swap_cannot_redirect_overlay_publication(self):
        plan, _, previous = self.changed_plan()
        lifecycle, moved = api.lifecycle_api(), self.root/'moved-references'
        original = lifecycle.publish
        swapped = False
        def race(fd, name, content, **kw):
            nonlocal swapped
            if kw['relative'] == TARGET and not swapped:
                swapped = True
                parent = (self.root/TARGET).parent
                parent.rename(moved)
                parent.mkdir()
                (parent/name).write_bytes(b'unrelated replacement directory')
            return original(fd, name, content, **kw)
        with mock.patch.object(api, 'lifecycle_api', return_value=lifecycle), mock.patch.object(lifecycle, 'publish', side_effect=race), self.assertRaises(api.InstallError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertEqual(b'unrelated replacement directory', (self.root/TARGET).read_bytes())
        self.assertEqual(previous, json.loads((self.root/api.MANIFEST_REL).read_text()))

    def test_payload_edit_after_publication_rolls_back_target_and_retains_source(self):
        plan, _, previous = self.changed_plan()
        before = (self.root/TARGET).read_bytes()
        lifecycle = api.lifecycle_api()
        original = lifecycle.publish
        edited = False
        def race(fd, name, content, **kw):
            nonlocal edited
            result = original(fd, name, content, **kw)
            if kw['relative'] == TARGET and not edited:
                edited = True
                (self.root/PAYLOAD).write_bytes(b'concurrent payload edit')
            return result
        with mock.patch.object(api, 'lifecycle_api', return_value=lifecycle), mock.patch.object(lifecycle, 'publish', side_effect=race), self.assertRaises(api.InstallError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertEqual(before, (self.root/TARGET).read_bytes())
        self.assertEqual(b'concurrent payload edit', (self.root/PAYLOAD).read_bytes())
        self.assertEqual(previous, json.loads((self.root/api.MANIFEST_REL).read_text()))

    def test_interrupt_rolls_back_multiple_files_preserving_contested_target(self):
        plan, _, previous = self.changed_plan()
        lifecycle = api.lifecycle_api()
        original = lifecycle.publish
        interrupted = False
        target_before = (self.root/TARGET).read_bytes()
        def interrupt(fd, name, content, **kw):
            nonlocal interrupted
            if kw['relative'] == api.MANIFEST_REL and not interrupted:
                interrupted = True
                (self.root/TARGET).write_bytes(b'user owns final edit')
                raise KeyboardInterrupt
            return original(fd, name, content, **kw)
        with mock.patch.object(api, 'lifecycle_api', return_value=lifecycle), mock.patch.object(lifecycle, 'publish', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertEqual(b'user owns final edit', (self.root/TARGET).read_bytes())
        self.assertEqual(previous, json.loads((self.root/api.MANIFEST_REL).read_text()))
        self.assertTrue(any(p.read_bytes() == target_before for p in (self.root/api.BACKUPS_REL).rglob('*.original')))

    def test_late_target_edit_during_ledger_publication_aborts_success(self):
        plan, _, previous = self.changed_plan()
        lifecycle = api.lifecycle_api()
        original = lifecycle.publish
        edited = False
        def race(fd, name, content, **kw):
            nonlocal edited
            result = original(fd, name, content, **kw)
            if kw['relative'] == api.MANIFEST_REL and not edited:
                edited = True
                (self.root/TARGET).write_bytes(b'late user output edit')
            return result
        with mock.patch.object(api, 'lifecycle_api', return_value=lifecycle), mock.patch.object(lifecycle, 'publish', side_effect=race), self.assertRaises(api.InstallError):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertEqual(b'late user output edit', (self.root/TARGET).read_bytes())
        self.assertEqual(previous, json.loads((self.root/api.MANIFEST_REL).read_text()))

    def test_root_replacement_after_planning_is_refused(self):
        self.manifest()
        plan, _, previous = self.plan()
        moved = self.base/'original-root'
        self.root.rename(moved)
        shutil.copytree(moved, self.root)
        with self.assertRaisesRegex(api.InstallError, 'root identity'):
            api.apply_plan(self.root, plan, previous, ['codex'], 'skills-only')
        self.assertFalse((self.root/TARGET).exists())

    def test_interrupted_multiple_writes_restore_independent_unchanged_outputs(self):
        self.changed_plan()
        original_projector = api.project_shared_skills
        second = '.agents/skills/sf-crawl/references/coverage.md'
        before = {path:(self.root/path).read_bytes() for path in (TARGET,second)}
        def changed_projector(hosts):
            return [dataclasses.replace(a, content=a.content+b'\nReviewed update.\n') if a.path == second else a
                    for a in original_projector(hosts)]
        lifecycle = api.lifecycle_api()
        original = lifecycle.publish
        def interrupt(fd, name, content, **kw):
            if kw['relative'] == api.MANIFEST_REL:
                raise KeyboardInterrupt
            return original(fd, name, content, **kw)
        with mock.patch.object(api,'project_shared_skills',side_effect=changed_projector):
            plan, conflicts, previous = self.plan()
            self.assertFalse(conflicts)
            with mock.patch.object(api,'lifecycle_api',return_value=lifecycle), mock.patch.object(lifecycle,'publish',side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
                api.apply_plan(self.root,plan,previous,['codex'],'skills-only')
        for path, raw in before.items():
            self.assertEqual(raw,(self.root/path).read_bytes())
        self.assertEqual(previous,json.loads((self.root/api.MANIFEST_REL).read_text()))

    def test_generated_upstream_change_after_planning_refuses_application(self):
        self.manifest()
        plan, _, previous = self.plan()
        original = api.project_shared_skills
        def changed(hosts):
            return [dataclasses.replace(a,content=a.content+b'upstream change') if a.path == TARGET else a for a in original(hosts)]
        with mock.patch.object(api,'project_shared_skills',side_effect=changed),self.assertRaises(api.InstallError):
            api.apply_plan(self.root,plan,previous,['codex'],'skills-only')
        self.assertFalse((self.root/TARGET).exists())

    def test_case_alias_and_declared_mcp_config_are_protected_targets(self):
        self.manifest()
        self.apply()
        self.data['documents']['principles']['risk'] = TARGET.replace('.agents','.AGENTS',1)
        self.write_config()
        # Declaration-only semantics also catch aliases on case-sensitive hosts.
        with self.assertRaises(config.ConfigError):
            config.validate_data(self.data,self.root,check_paths=False)
        lifecycle = api.lifecycle_api()
        before = (self.root/TARGET).read_bytes()
        with (mock.patch.object(api,'lifecycle_api',return_value=lifecycle),
              mock.patch.object(lifecycle,'publish',side_effect=AssertionError('governing target publication attempted')),
              self.assertRaises(api.InstallError)):
            self.plan()
        self.assertEqual(before,(self.root/TARGET).read_bytes())
        self.data['documents']['principles']['risk'] = 'RISK.md'
        self.data['extensions']['mcp'] = [{'id':'sample','config':TARGET,'enabled':False}]
        self.write_config()
        with self.assertRaises(api.InstallError):
            self.plan()
