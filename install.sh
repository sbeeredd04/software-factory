#!/bin/sh
# Pinned, integrity-checked release bootstrap; local checkouts stay offline.
set -eu
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Software Factory requires Python 3.11 or newer; install it, then retry.' >&2
  exit 1
fi
exec python3 - "$0" "$@" <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit('Software Factory requires Python 3.11 or newer; install it, then retry.')
import gzip
import hashlib
import os
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

DEFAULT_REF = 'v0.1.0'
RELEASE_BASE = 'https://github.com/sbeeredd04/software-factory/releases/download'
MAX_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 10000


def interrupted(number, _frame):
    raise SystemExit(128 + number)


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)


def bounded_tar(archive):
    # Bound the entire decoded stream, including metadata and padding, before
    # tarfile can consume hidden PAX/GNU headers or allocate their payloads.
    unpacked = archive.with_suffix('.tar.raw')
    total = 0
    with gzip.open(archive, 'rb') as source, unpacked.open('xb') as target:
        while chunk := source.read(min(65536, MAX_BYTES - total + 1)):
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError('archive exceeds extraction limits (raw tar bytes)')
            target.write(chunk)
    with unpacked.open('rb') as source:
        count, ended = 0, False
        while header := source.read(512):
            if len(header) != 512:
                raise ValueError('truncated archive header')
            if header == bytes(512):
                ended = True
                continue
            if ended:
                raise ValueError('nonzero data after archive terminator')
            # These are the only header types produced by our USTAR builder.
            # NUL/V7 headers are excluded: tarfile can reinterpret a name ending
            # in '/' as a directory and stop skipping its declared payload.
            # Accept only explicit regular files/directories, with identical
            # payload boundaries in this scan and tarfile's builtin processing.
            if header[156:157] not in (b'0', b'5'):
                raise ValueError('unsafe archive header type (extensions unsupported)')
            count += 1
            # Parse this fixed header only, using exactly the same numeric and
            # checksum semantics as the later TarFile reader. frombuf does not
            # read or process extension payloads; their types were rejected above.
            member = tarfile.TarInfo.frombuf(header, tarfile.ENCODING, 'surrogateescape')
            size = member.size
            if count > MAX_MEMBERS or size < 0 or size > MAX_BYTES:
                raise ValueError('archive exceeds extraction limits')
            padded = ((size + 511) // 512) * 512
            if source.tell() + padded > total:
                raise ValueError('truncated archive member')
            if header[156:157] == b'5' and size:
                raise ValueError('directory archive member has data')
            source.seek(padded, 1)
        if not ended:
            raise ValueError('archive terminator missing')
    return unpacked


def extract(archive, destination, ref):
    expected = 'sf-' + ref
    with tarfile.open(bounded_tar(archive), 'r:') as source:
        members, seen, total = [], {}, 0
        for member in source:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != expected or member.name.startswith('/')
                    or '\\' in member.name or any(p in ('.', '..') for p in member.name.split('/'))
                    or not (member.isfile() or member.isdir()) or member.issparse()):
                raise ValueError('unsafe archive member')
            name = '/'.join(parts)
            if name in seen or any(seen.get('/'.join(parts[:i])) == 'file'
                                   for i in range(1, len(parts))):
                raise ValueError('archive path collision')
            if member.isfile() and any(p.startswith(name + '/') for p in seen):
                raise ValueError('archive path collision')
            seen[name] = 'file' if member.isfile() else 'directory'
            total += member.size
            members.append(member)
            if len(members) > MAX_MEMBERS or total > MAX_BYTES or member.size < 0:
                raise ValueError('archive exceeds extraction limits')
        if seen.get(expected + '/install.py') != 'file':
            raise ValueError('archive is missing the expected installer')
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return destination / expected / 'install.py'


def main():
    args, forwarded, ref = sys.argv[2:], [], DEFAULT_REF
    while args:
        arg, args = args[0], args[1:]
        if arg == '--ref':
            if not args:
                raise ValueError('--ref requires a release tag')
            ref, args = args[0], args[1:]
        elif arg.startswith('--ref='):
            ref = arg.partition('=')[2]
        else:
            forwarded.append(arg)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', ref) or '..' in ref:
        raise ValueError('invalid release ref')
    if not any(a == '--project' or a.startswith('--project=') for a in forwarded):
        forwarded.extend(['--project', str(Path.cwd())])
    local = Path(sys.argv[1]).resolve().with_name('install.py')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if local.is_file():
        return subprocess.call([sys.executable, str(local), 'install', *forwarded], env=env)
    if not shutil.which('curl'):
        raise ValueError('curl is required to download a release; use a local checkout offline')
    with tempfile.TemporaryDirectory(prefix='sf-bootstrap-') as temporary:
        stage = Path(temporary)
        archive_name = 'sf-' + ref + '.tar.gz'
        for name in (archive_name, 'SHA256SUMS'):
            subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                            '--proto', '=https', '--proto-redir', '=https',
                            '--max-time', '120', '--max-filesize', str(MAX_BYTES),
                            '--output', str(stage / name), RELEASE_BASE + '/' + ref + '/' + name],
                           check=True)
        sums = stage / 'SHA256SUMS'
        if sums.stat().st_size > 1024 * 1024:
            raise ValueError('checksum file exceeds limit')
        matches = []
        for line in sums.read_text(encoding='ascii').splitlines():
            match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *]([^\s]+)', line)
            if not match:
                raise ValueError('malformed checksum entry')
            if match[2] == archive_name:
                matches.append(match[1].lower())
        if len(matches) != 1:
            raise ValueError('missing or duplicate archive checksum')
        archive = stage / archive_name
        if archive.stat().st_size > MAX_BYTES:
            raise ValueError('archive exceeds download limit')
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != matches[0]:
            raise ValueError('archive checksum mismatch')
        installer = extract(archive, stage / 'unpacked', ref)
        return subprocess.call([sys.executable, str(installer), 'install', *forwarded], env=env)


try:
    sys.exit(main())
except (OSError, EOFError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as exc:
    sys.exit('Software Factory bootstrap: ' + str(exc))
PY
