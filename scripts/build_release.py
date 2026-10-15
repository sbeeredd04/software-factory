"""Build a local reproducible release from the reviewed public file allowlist."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
import tempfile
from pathlib import Path

import distribution


def release_files(api):
    root = api.PACK_ROOT
    names = json.loads((root / 'hosts/plugins/release-files.json').read_text())
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError('release allowlist must be a list of paths')
    if len(names) != len(set(names)):
        raise ValueError('duplicate release allowlist path')
    files = {}
    for name in names:
        path = root / name
        if (name.startswith('/') or '..' in Path(name).parts
                or path.is_symlink() or any(p.is_symlink() for p in path.parents)
                or not path.is_file() or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('invalid release allowlist source')
        files[name] = path.read_bytes()
    # Native projectors recurse through skills. Give them only the captured
    # reviewed bytes, never the live checkout (which may contain local notes).
    with tempfile.TemporaryDirectory(prefix='sf-release-source-') as temporary:
        snapshot = Path(temporary).resolve()
        for name, data in files.items():
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        snapshot_api = distribution.load_api(snapshot)
        for host in distribution.HOSTS:
            files.update({f'dist/plugins/{host}/{name}': data
                          for name, data in distribution.bundle_files(snapshot_api, host).items()})
    return files


def archive_bytes(files, ref):
    result = io.BytesIO()
    with (gzip.GzipFile(fileobj=result, mode='wb', filename='', mtime=0) as zipped,
          tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as archive):
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo('sf-' + ref + '/' + name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            info.mtime = info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    return result.getvalue()


def build(api, out, ref):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', ref):
        raise ValueError('release ref must be a version tag')
    if ref != 'v' + api.PACK_VERSION:
        raise ValueError('release ref must match the pack version')
    name = 'sf-' + ref + '.tar.gz'
    archive = archive_bytes(release_files(api), ref)
    sums = hashlib.sha256(archive).hexdigest() + '  ' + name + '\n'
    return distribution.write_new(out, {name: archive, 'SHA256SUMS': sums.encode()}, api.PACK_ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ref', default='v0.1.0')
    args = parser.parse_args()
    try:
        build(distribution.load_api(), args.out, args.ref)
    except (OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(1, f'release: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
