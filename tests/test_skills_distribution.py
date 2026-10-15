"""Network-marked proof of the real third-party local-path skills route."""
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO, fresh_repo, guard_env

SKILLS_VERSION = '1.7.2'


def documented_route(document, source):
    """Validate the documented literal grammar, then substitute fixture paths."""
    section = document.split('## Canonical skills CLI route\n', 1)[1]
    block = re.search(r'```sh\n(.*?)\n```', section, re.DOTALL)
    if block is None:
        raise ValueError('canonical acquisition block missing')
    commands = [shlex.split(line) for line in block.group(1).splitlines()]
    prefix = ['DISABLE_TELEMETRY=1', 'DO_NOT_TRACK=1', 'npx', '-y',
              'skills@'+SKILLS_VERSION, 'add', '/absolute/path/to/software-factory/skills']
    expected = [
        ['cd', '/absolute/path/to/consumer-project', '||', 'exit', '1'],
        prefix+['--list'],
        prefix+['-a', 'claude-code', '-a', 'cursor', '-a', 'codex', '-y'],
    ]
    if commands != expected:
        raise ValueError('documented acquisition command drift')
    # No shell or document-supplied command is executed. The independent grammar
    # fixes the executable/version/hosts; only owned fixture paths are substituted.
    result = [command[5:] for command in commands[1:]]
    for args in result:
        args[1] = str(source)
    return result


class DocumentedRouteTests(unittest.TestCase):
    def test_exact_route_and_cwd_refuse_document_only_drift(self):
        document = (REPO/'docs/distribution.md').read_text()
        source = Path('/fixture with spaces/skills')
        args = documented_route(document, source)
        self.assertEqual(args[0], ['add', str(source), '--list'])
        self.assertEqual(args[1], ['add', str(source), '-a', 'claude-code',
                                  '-a', 'cursor', '-a', 'codex', '-y'])
        for mutated in (
            document.replace('/software-factory/skills', '/software-factory'),
            document.replace(" || exit 1", '', 1),
            document.replace('-a codex', '-a other', 1),
        ):
            with self.subTest(mutated=mutated[-80:]), self.assertRaises(ValueError):
                documented_route(mutated, source)


@unittest.skipIf(os.environ.get('SF_SKIP_NETWORK') == '1', 'network-marked skills CLI: skipped, unverified')
class SkillsDistributionTests(unittest.TestCase):
    def test_real_local_list_and_all_host_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            env, log, guards = guard_env()
            self.addCleanup(shutil.rmtree, guards)
            for name in ('agent', 'droid', 'claude-code'):
                stub = guards/name
                stub.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$SF_GUARD_LOG"\nexit 127\n')
                stub.chmod(0o755)
            home = root/'isolated-home'
            home.mkdir()
            env.update(HOME=str(home), CODEX_HOME=str(home/'.codex'),
                       DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', CI='1',
                       npm_config_cache=str(root/'npm-cache'), npm_config_update_notifier='false')
            expected = {p.parent.name: p.read_text() for p in (REPO/'skills').glob('*/SKILL.md')}
            self.assertEqual(len(expected), 11)
            configured = root/'configured pack'
            shutil.copytree(REPO/'skills', configured/'skills')
            unrelated = configured/'.agents/skills/unrelated-fixture/SKILL.md'
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text('---\nname: unrelated-fixture\n'
                                 'description: Unrelated locally installed fixture skill.\n'
                                 '---\n\nNot part of the canonical pack.\n')

            def run(consumer, *args):
                result = subprocess.run(['npx','-y','skills@'+SKILLS_VERSION,*args], cwd=consumer,
                                        env=env, text=True, check=False, capture_output=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
                return result.stdout

            for index, source in enumerate((REPO/'skills', configured/'skills')):
                with self.subTest(source=index):
                    consumer = fresh_repo(root, name=f'consumer {index}')
                    version = run(consumer, '--version').strip()
                    self.assertIn(SKILLS_VERSION, version)
                    print('skills CLI version: '+version, flush=True)
                    list_args, install_args = documented_route(
                        (REPO/'docs/distribution.md').read_text(), source)
                    listing = run(consumer, *list_args)
                    for name in expected:
                        self.assertIn(name, listing)
                    self.assertNotIn('unrelated-fixture', listing)
                    run(consumer, *install_args)
                    for target in ('.claude/skills','.agents/skills'):
                        folder = consumer/target
                        self.assertEqual({p.name for p in folder.iterdir()}, set(expected))
                        for name, canonical in expected.items():
                            # Follow legitimate CLI symlinks; verify canonical identity bytes.
                            self.assertEqual((folder/name/'SKILL.md').read_text(), canonical)
                    self.assertTrue((consumer/'skills-lock.json').is_file())
                    self.assertFalse((consumer/'.cursor').exists())
                    self.assertFalse((consumer/'.codex').exists())
            self.assertFalse(log.exists() and log.stat().st_size, 'host CLI was invoked')


if __name__ == '__main__':
    unittest.main()
