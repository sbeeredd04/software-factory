"""Deterministic observations, permission-aware routing and unexecuted argv."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support


def helper(name):
    return support.helper('config') if name == 'config' else load_module(support.REPO/'skills/sf-agents/scripts'/f'{name}.py', 'test_sf_'+name)


def load_module(path, name):
    import importlib.util
    import sys
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name,path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


A = helper('agents')


def fixture(root, bots=False):
    root.mkdir(parents=True,exist_ok=True)
    for path in (support.REPO/'examples/config').glob('*.md'):
        shutil.copyfile(path,root/path.name)
    data = json.loads((support.REPO/'examples/config/config.yaml').read_text())
    data['project']['root'] = '..'
    if bots:
        targets = {'greptile':'.greptile/config.json','coderabbit':'.coderabbit.yaml','bugbot':'.cursor/BUGBOT.md','copilot':'.github/copilot-instructions.md'}
        data['review_bots'] = {b:{'enabled':True,'required':False,'config':p,'authors':['fixture-review[bot]']} for b,p in targets.items()}
    save(root,data)
    return data


def save(root,data):
    (root/'.software-factory').mkdir(exist_ok=True)
    (root/A.discovery.CONFIG).write_text(json.dumps(data,indent=2)+'\n')


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'
        self.data = fixture(self.root)

    def external(self):
        self.data['agents']['cursor'] = {'kind':'external','description':'Configured external worker','risk_tiers':[0,1],
            'detection':{'kind':'executable-presence','executable':'cursor-agent'},
            'invoke':{'argv':['cursor-agent','-p','--workspace','{workspace}','{task_file}'],'cwd':'.','operation':'write'}}
        self.data['routing']['coding'] = 'cursor'
        self.data['routing']['complexity']['low'] = 'cursor'
        save(self.root,self.data)

    def test_presence_never_executes_guards_or_invents_auth_version_model(self):
        self.external()
        binary = Path(self.temp.name)/'bin'
        binary.mkdir()
        for name in ('claude','cursor-agent','codex','agent','gh'):
            path = binary/name
            path.write_text('#!/bin/sh\nexit 99\n')
            path.chmod(0o755)
        before = support.tree_hashes(self.root)
        with mock.patch('subprocess.Popen',side_effect=AssertionError('executed probe')):
            result = A.presence(self.root,path=str(binary),inventory={'native':True})
        self.assertTrue(result['agents']['cursor']['present'])
        self.assertTrue(result['gh']['present'])
        for field in ('auth','version','effective_model'):
            self.assertIsNone(result['agents']['cursor'][field])
        self.assertEqual(before,support.tree_hashes(self.root))
        self.assertFalse(A.presence(self.root,path='')['agents']['cursor']['present'])
        self.assertIsNone(A.presence(self.root,path='')['agents']['native']['present'])

    def test_risk_complexity_native_fallback_with_actual_scope(self):
        self.external()
        for risk in range(4):
            for complexity in ('low','medium','high'):
                result = A.route(self.root,risk=risk,complexity=complexity,operation='write',phase='coding',
                    observations=A.presence(self.root,path=''),permissions={'native':'workspace-write'})
                self.assertEqual('native',result['selected'])
                self.assertEqual('native',result['chain'][-1])
                self.assertIsNone(result['effective_model'])
                self.assertIn('risk',result['rationale'])

    def test_permission_denial_and_unknown_never_evaded(self):
        for denied in (True,False):
            result = A.route(self.root,risk=2,complexity='high',operation='observe',phase='review',
                observations=A.presence(self.root,path=''),permissions={'native':'workspace-write'},denied=denied)
            self.assertIsNone(result['selected'])
        result = A.route(self.root,risk=2,complexity='high',operation='observe',phase='review',
            observations=A.presence(self.root,path=''),permissions={'native':'read-only'})
        self.assertEqual('native',result['selected'])

    def test_presence_stale_config_and_false_native_inventory(self):
        observed = A.presence(self.root,path='')
        self.data['project']['name'] = 'Changed'
        save(self.root,self.data)
        with self.assertRaises(A.Error):
            A.route(self.root,risk=0,complexity='low',operation='observe',phase='analysis',observations=observed)
        with self.assertRaises(A.Error):
            A.presence(self.root,inventory={'native':'yes'})

    def test_known_file_rejects_symlink_fifo_and_nonexistent_is_absent(self):
        self.data['agents']['native']['detection'] = {'kind':'known-file','path':'capability.json'}
        save(self.root,self.data)
        self.assertFalse(A.presence(self.root,path='')['agents']['native']['present'])
        target = self.root/'capability.json'
        target.symlink_to(self.root/'PRODUCT.md')
        with self.assertRaises(ValueError):
            A.presence(self.root)
        target.unlink()
        import os
        os.mkfifo(target)
        with self.assertRaises(ValueError):
            A.presence(self.root)

    def test_literal_argv_spaces_shell_characters_and_no_model_guess(self):
        self.external()
        task = 'task with spaces; $(do-not-run) `literal`'
        with mock.patch('subprocess.Popen',side_effect=AssertionError('dispatch')):
            result = A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':task})
        self.assertEqual(['cursor-agent','-p','--workspace',str(self.root),task],result['argv'])
        self.assertIsNone(result['effective_model'])
        self.assertEqual('rendered-unexecuted',result['status'])
        with self.assertRaises(A.Error):
            A.invocation(self.root,'cursor',{'{workspace}':str(self.root)})
        with self.assertRaises(A.Error):
            A.invocation(self.root,'cursor',{'{workspace}':str(self.root.parent),'{task_file}':'task'})

    def test_declared_force_does_not_become_dispatch_ready(self):
        self.external()
        self.data['agents']['cursor']['invoke']['argv'].append('--force')
        save(self.root,self.data)
        with self.assertRaises(A.Error):
            A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'task'})

    def test_codex_literal_sandbox_mapping_cannot_weaken_observe(self):
        self.external()
        agent = self.data['agents']['cursor']
        agent['invoke'] = {'argv':['codex','exec','--sandbox','read-only','--cd','{workspace}','{task_file}'],'cwd':'.','operation':'observe'}
        save(self.root,self.data)
        value = A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'brief.md'})
        self.assertEqual(['codex','exec','--sandbox','read-only','--cd',str(self.root),'brief.md'],value['argv'])
        agent['invoke']['argv'][3] = 'workspace-write'
        save(self.root,self.data)
        with self.assertRaises(A.Error):
            A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'brief.md'})

    def test_ambiguous_scope_options_and_option_substitutions_refused(self):
        self.external()
        agent = self.data['agents']['cursor']
        for extra in ('--sandbox=workspace-write','--cd=/outside','-C/outside','-sworkspace-write','-csetting=value','--full-auto','--add-dir=/outside'):
            agent['invoke'] = {'argv':['codex','exec','--sandbox','read-only','--cd','{workspace}','{task_file}',extra],'cwd':'.','operation':'observe'}
            save(self.root,self.data)
            with self.subTest(extra=extra),self.assertRaises(A.Error):
                A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'brief.md'})
        for extra in ('--sandbox=disabled','--mode=agent','--workspace=/outside'):
            agent['invoke'] = {'argv':['cursor-agent','--workspace','{workspace}','--mode','ask','{task_file}',extra],'cwd':'.','operation':'observe'}
            save(self.root,self.data)
            with self.subTest(extra=extra),self.assertRaises(A.Error):
                A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'brief.md'})
        agent['invoke']['argv'].pop()
        save(self.root,self.data)
        with self.assertRaises(A.Error):
            A.invocation(self.root,'cursor',{'{workspace}':str(self.root),'{task_file}':'--force'})

    def test_installed_only_helpers_with_host_guards_and_hostile_modules(self):
        import subprocess
        import sys
        env, guard, binary = support.guard_env()
        self.addCleanup(shutil.rmtree,binary,ignore_errors=True)
        for host in ('claude-code','cursor','codex'):
            project = Path(self.temp.name)/host
            fixture(project,True)
            result = support.run_installer('install','--project',project,'--host',host,'--skip-bmad',env=env)
            self.assertEqual(0,result.returncode,result.stderr)
            skills = project/('.claude/skills' if host == 'claude-code' else '.agents/skills')
            (project/'json.py').write_text('raise RuntimeError("consumer import")')
            for script, args in (('agents',['discover']),('render_bots',['plan','--bots','copilot','--principles-ref','decision:approved'])):
                result = subprocess.run([sys.executable,'-I','-B',str(skills/'sf-agents/scripts'/f'{script}.py'),'--project',str(project),*args],
                    cwd=project,env=env,capture_output=True,text=True,check=False)
                self.assertEqual(0,result.returncode,result.stderr)
            self.assertTrue((skills/'sf-agents/scripts/install_lifecycle.py').is_file())
            renderer = load_module(skills/'sf-agents/scripts/render_bots.py','installed_missing_'+host)
            (skills/'sf-agents/scripts/install_lifecycle.py').unlink()
            fallback = skills.parent/'scripts/install_lifecycle.py'
            fallback.parent.mkdir(exist_ok=True)
            fallback.write_text('raise AssertionError("consumer fallback executed")')
            with self.assertRaisesRegex(renderer.Error,'installed dependency missing'):
                renderer.lifecycle()
            shutil.rmtree(skills/'sf-agents/templates')
            with self.assertRaisesRegex(renderer.Error,'installed dependency missing'):
                renderer.plan(project,['copilot'],'decision:approved')
        self.assertFalse(guard.exists())
