"""POSIX bootstrap fixtures never contact a remote or run a host CLI."""
import gzip
import hashlib
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

from support import REPO, tree_hashes


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.pack = self.root/'standalone'
        self.pack.mkdir()
        shutil.copyfile(REPO/'install.sh', self.pack/'install.sh')
        self.consumer = self.root/'consumer with spaces'
        self.consumer.mkdir()
        self.stage = self.root/'staging'
        self.stage.mkdir()
        self.bins = self.root/'bin'
        self.bins.mkdir()
        (self.bins/'python3').symlink_to(sys.executable)
        self.log = self.root/'urls.jsonl'
        self.executed = self.root/'executed.json'
        curl = self.bins/'curl'
        curl.write_text('#!'+sys.executable+'\n'+
                        'import json,os,sys,shutil\nfrom pathlib import Path\n'
                        'with open(os.environ["URL_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                        'if os.environ.get("FAIL_CURL"): sys.exit(22)\n'
                        'shutil.copyfile(Path(os.environ["FIXTURES"])/sys.argv[-1].rsplit("/",1)[1],sys.argv[sys.argv.index("--output")+1])\n')
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bins)+os.pathsep+os.environ['PATH'],
                        TMPDIR=str(self.stage), URL_LOG=str(self.log), FIXTURES=str(self.root),
                        EXECUTED=str(self.executed))

    def run_bootstrap(self, *args, env=None):
        result = subprocess.run(['/bin/sh', str(self.pack/'install.sh'), *args],
                                cwd=self.consumer, env=env or self.env, text=True, check=False, capture_output=True, timeout=30)
        self.assertEqual(list(self.stage.iterdir()), [], 'temporary staging leaked')
        return result

    def fixture(self, members=None, ref='v0.1.0', script=None):
        if script is None:
            script = ('import json,os,sys\n'
                      'from pathlib import Path\n'
                      'Path(os.environ["EXECUTED"]).write_text(json.dumps(sys.argv[1:]))\n')
        path = self.root/('sf-'+ref+'.tar.gz')
        with tarfile.open(path, 'w:gz') as archive:
            if members is None:
                members = [('sf-'+ref+'/install.py', script.encode(), tarfile.REGTYPE)]
            for name, data, kind in members:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(data) if kind == tarfile.REGTYPE else 0
                if kind in (tarfile.LNKTYPE, tarfile.SYMTYPE):
                    info.linkname = '/outside'
                archive.addfile(info, io.BytesIO(data) if info.size else None)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root/'SHA256SUMS').write_text(digest+'  '+path.name+'\n')
        return path

    def test_valid_default_and_explicit_ref_urls_forwarding(self):
        for ref in ('v0.1.0', 'v1.2.3'):
            self.fixture(ref=ref)
            result = self.run_bootstrap(*(['--ref',ref] if ref != 'v0.1.0' else []), '--host','all','--dry-run')
            self.assertEqual(result.returncode, 0, result.stderr)
            argv = json.loads(self.executed.read_text())
            self.assertEqual(argv, ['install','--host','all','--dry-run','--project',str(self.consumer)])
            urls = [json.loads(line)[-1] for line in self.log.read_text().splitlines()][-2:]
            self.assertEqual(urls, [f'https://github.com/sbeeredd04/software-factory/releases/download/{ref}/'+name
                                    for name in ('sf-'+ref+'.tar.gz','SHA256SUMS')])

    def test_tamper_stops_before_installer(self):
        path = self.fixture()
        path.write_bytes(path.read_bytes()+b'x')
        result = self.run_bootstrap('--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertFalse(self.executed.exists())

    def test_checksum_missing_duplicate_malformed(self):
        self.fixture()
        valid = (self.root/'SHA256SUMS').read_text()
        for value in ('', valid+valid, 'bad checksum\n', valid.replace('sf-v0.1.0','other')):
            (self.root/'SHA256SUMS').write_text(value)
            result = self.run_bootstrap()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('checksum', result.stderr)
            self.assertFalse(self.executed.exists())

    def test_ref_validation_before_download(self):
        for args in (('--ref',), ('--ref',''), ('--ref','../escape'), ('--ref','https://other'), ('--ref=x;echo hacked',)):
            result = self.run_bootstrap(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())

    def test_network_failure_missing_downloads_and_invalid_tar(self):
        self.fixture()
        result = self.run_bootstrap(env=dict(self.env, FAIL_CURL='1'))
        self.assertNotEqual(result.returncode, 0)
        for name in ('SHA256SUMS','sf-v0.1.0.tar.gz'):
            self.fixture()
            (self.root/name).unlink()
            self.assertNotEqual(self.run_bootstrap().returncode, 0)
        archive = self.fixture()
        archive.write_bytes(b'not tar')
        (self.root/'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
        self.assertNotEqual(self.run_bootstrap().returncode, 0)
        self.assertFalse(self.executed.exists())

    def test_malicious_archives_never_execute(self):
        installer = ('sf-v0.1.0/install.py', b'raise SystemExit(99)', tarfile.REGTYPE)
        malicious = [('../escape', b'', tarfile.REGTYPE), ('/absolute', b'', tarfile.REGTYPE),
                     ('sf-v0.1.0/../escape',b'',tarfile.REGTYPE), ('sf-v0.1.0/link',b'',tarfile.SYMTYPE),
                     ('sf-v0.1.0/hard',b'',tarfile.LNKTYPE), ('sf-v0.1.0/dev',b'',tarfile.CHRTYPE),
                     ('sf-v0.1.0/fifo',b'',tarfile.FIFOTYPE), installer]
        for member in malicious:
            self.fixture([installer, member])
            result = self.run_bootstrap()
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(self.executed.exists())
        for members in ([('wrong/install.py',b'',tarfile.REGTYPE)],
                        [installer, ('sf-v0.1.0/a/b',b'',tarfile.REGTYPE), ('sf-v0.1.0/a',b'',tarfile.REGTYPE)]):
            self.fixture(members)
            self.assertEqual(self.run_bootstrap().returncode, 1)

    def test_declared_expanded_size_bound(self):
        archive = self.root/'sf-v0.1.0.tar.gz'
        info = tarfile.TarInfo('sf-v0.1.0/oversized')
        info.size = 128 * 1024 * 1024 + 1
        archive.write_bytes(gzip.compress(info.tobuf()))
        (self.root/'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
        result = self.run_bootstrap()
        self.assertIn('extraction limits', result.stderr)
        self.assertFalse(self.executed.exists())

    def test_missing_curl_has_actionable_failure(self):
        bins = self.root/'python-only'
        bins.mkdir()
        (bins/'python3').symlink_to(sys.executable)
        result = self.run_bootstrap(env=dict(self.env, PATH=str(bins)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('curl is required', result.stderr)

    def test_member_count_limit(self):
        self.fixture([(f'sf-v0.1.0/f{i}',b'',tarfile.REGTYPE) for i in range(10001)])
        result = self.run_bootstrap()
        self.assertIn('extraction limits', result.stderr)
        self.assertFalse(self.executed.exists())

    def test_local_offline_quoting_and_explicit_project(self):
        self.fixture()
        (self.pack/'install.py').write_text('import json,os,sys\nfrom pathlib import Path\n'
                                          'Path(os.environ["EXECUTED"]).write_text(json.dumps(sys.argv[1:]))\n')
        forwarded = ['--project',str(self.consumer/'literal $x; `touch x`'), '--host','all','--skip-bmad','--dry-run']
        result = self.run_bootstrap('--ref','v9.0.0',*forwarded,env=dict(self.env,FAIL_CURL='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.executed.read_text()), ['install',*forwarded])
        self.assertFalse(self.log.exists())
        self.assertEqual(list(self.consumer.iterdir()), [])

    def test_real_release_dry_run_preserves_consumer(self):
        sys.path.insert(0,str(REPO/'scripts'))
        import build_release
        import distribution
        api = distribution.load_api()
        release = build_release.build(api,self.root/'release','v'+api.PACK_VERSION)
        for path in release.iterdir():
            shutil.copyfile(path,self.root/path.name)
        before = tree_hashes(self.consumer)
        result = self.run_bootstrap('--host','all','--skip-bmad','--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('dry', result.stdout.lower())
        self.assertEqual(before, tree_hashes(self.consumer))
        self.assertFalse(self.executed.exists())

    def test_python_absent_or_old_reports_requirement(self):
        empty = self.root/'empty'
        empty.mkdir()
        for old in (False, True):
            if old:
                python = empty/'python3'
                python.write_text('#!'+sys.executable+'\nimport sys\nsys.version_info=(3,9)\nexec(sys.stdin.read())\n')
                python.chmod(0o755)
            result = self.run_bootstrap(env=dict(self.env,PATH=str(empty)))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Python 3.11', result.stderr)


if __name__ == '__main__':
    unittest.main()
