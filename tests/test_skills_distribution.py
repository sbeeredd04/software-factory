"""Network-marked proof of the real third-party local-path skills route."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO, fresh_repo, guard_env

SKILLS_VERSION = '1.7.2'


@unittest.skipIf(os.environ.get('SF_SKIP_NETWORK') == '1', 'network-marked skills CLI: skipped, unverified')
class SkillsDistributionTests(unittest.TestCase):
    def test_real_local_list_and_all_host_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            consumer = fresh_repo(root)
            env, log, guards = guard_env()
            self.addCleanup(shutil.rmtree, guards)
            home = root/'isolated-home'
            home.mkdir()
            env.update(HOME=str(home), DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', CI='1',
                       npm_config_cache=str(root/'npm-cache'), npm_config_update_notifier='false')
            expected = {p.parent.name: p.read_text() for p in (REPO/'skills').glob('*/SKILL.md')}
            self.assertEqual(len(expected), 11)

            def run(*args):
                result = subprocess.run(['npx','-y','skills@'+SKILLS_VERSION,*args], cwd=consumer,
                                        env=env, text=True, check=False, capture_output=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
                return result.stdout

            version = run('--version').strip()
            self.assertIn(SKILLS_VERSION, version)
            print('skills CLI version: '+version, flush=True)
            listing = run('add',str(REPO),'--list')
            for name in expected:
                self.assertIn(name, listing)
            run('add',str(REPO),'-a','claude-code','-a','cursor','-a','codex','-y')
            for target in ('.claude/skills','.agents/skills'):
                folder = consumer/target
                self.assertEqual({p.name for p in folder.iterdir()}, set(expected))
                for name, canonical in expected.items():
                    # Follow legitimate CLI symlinks; exact bytes also prove identity fields.
                    self.assertEqual((folder/name/'SKILL.md').read_text(), canonical)
            self.assertTrue((consumer/'skills-lock.json').is_file())
            self.assertFalse((consumer/'.cursor').exists())
            self.assertFalse((consumer/'.codex').exists())
            self.assertFalse(log.exists() and log.stat().st_size, 'host CLI was invoked')


if __name__ == '__main__':
    unittest.main()
