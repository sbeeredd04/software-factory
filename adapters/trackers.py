"""Bounded planning-source observations and owner-mediated patch proposals.

This helper never writes trackers or board records, executes workflows, or
verifies a gate. A proposal requires subject-bound evidence references; the
owning workflow must verify applicability and authority before applying it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_LINES = 10000
STORY = re.compile(r'[0-9]+-[0-9]+-[a-z0-9][a-z0-9-]*\Z')
STATUSES = {'backlog', 'ready-for-dev', 'in-progress', 'review', 'done'}
MD_TASK = re.compile(r'^- \[([ xX])\] ([A-Z][A-Z0-9-]{0,63}): (.+?) \| ac: ([^|]+) \| depends: (.+?)(\r?\n)?$')
SHA = re.compile(r'[0-9a-f]{64}\Z')


class TrackerError(ValueError):
    pass


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def lines(text):
    if len(text.encode('utf-8')) > MAX_BYTES or len(text.splitlines()) > MAX_LINES or '\x00' in text:
        raise TrackerError('tracker exceeds bounds or contains binary data')
    return text.splitlines(keepends=True)


def observe_v6(text):
    rows = lines(text)
    entries, links, actions, seen = [], {}, [], set()
    section = None
    metadata = {'generated', 'project', 'project_key', 'tracking_system', 'story_location'}
    for number, line in enumerate(rows, 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '\t' in line or any(c in line for c in ('&', '*', '!', '|', '>')):
            raise TrackerError(f'line {number}: unsupported sprint-status YAML syntax')
        if line.startswith('  - ') and section == 'action_items':
            item = line[4:].strip()
            if not item:
                raise TrackerError(f'line {number}: empty action item')
            actions.append({'text': item, 'line': number})
            continue
        match = re.fullmatch(r'( {0,2})([A-Za-z0-9_-]+):(?: ([^\r\n]*))?\r?\n?', line)
        if not match or len(match[1]) not in (0, 2):
            raise TrackerError(f'line {number}: unsupported mapping')
        indent, key, raw = match.groups()
        if not indent:
            if key in seen:
                raise TrackerError(f'line {number}: duplicate top-level key')
            seen.add(key)
            if key in ('development_status', 'planning_artifacts', 'action_items') and not raw:
                section = key
                continue
            if key not in metadata or not raw:
                raise TrackerError(f'line {number}: unsupported top-level field')
            section = None
            continue
        if section == 'planning_artifacts':
            if key in links or not raw:
                raise TrackerError(f'line {number}: duplicate or missing planning link')
            links[key] = raw.split(' #', 1)[0].strip()
            continue
        if section != 'development_status' or not raw:
            raise TrackerError(f'line {number}: unsupported nested field')
        status = raw.split(' #', 1)[0].strip()
        if any(e['source_key'] == key for e in entries):
            raise TrackerError(f'line {number}: duplicate status key')
        kind = 'story' if STORY.fullmatch(key) else 'epic' if re.fullmatch(r'epic-[0-9]+', key) else 'retrospective' if re.fullmatch(r'epic-[0-9]+-retrospective', key) else None
        allowed = STATUSES if kind == 'story' else {'backlog', 'in-progress', 'done'} if kind == 'epic' else {'optional', 'done', 'required'}
        if not kind or status not in allowed:
            raise TrackerError(f'line {number}: unsupported status entry')
        entries.append({'source_key':key, 'kind':kind, 'observed_status':status, 'line':number})
    if 'development_status' not in seen:
        raise TrackerError('development_status is required')
    return {'adapter':'bmad-v6','authority':'planning-source-observation','source_sha256':digest(text),
            'entries':entries,'planning_links':links,'action_items':actions}


def observe_markdown(text):
    entries = []
    seen = set()
    for number, line in enumerate(lines(text), 1):
        match = MD_TASK.fullmatch(line)
        if not match:
            if re.match(r'^\s*- \[[ xX]\]', line):
                raise TrackerError(f'line {number}: task needs explicit ID, AC links and dependencies')
            continue
        checked, key, title, ac, dependencies, _ = match.groups()
        if key in seen:
            raise TrackerError(f'line {number}: duplicate task ID')
        seen.add(key)
        deps = [] if dependencies == '-' else dependencies.split(',')
        if any(not re.fullmatch(r'[A-Z][A-Z0-9-]{0,63}', d) for d in deps):
            raise TrackerError(f'line {number}: invalid dependency ID')
        acceptance = [p.strip() for p in ac.split(',')]
        if not all(acceptance):
            raise TrackerError(f'line {number}: acceptance references must be nonempty')
        entries.append({'source_key':key,'kind':'story','title':title,'observed_status':'done' if checked.lower() == 'x' else 'backlog', 'line':number,'acceptance_links':acceptance, 'depends_on':deps})
    if any(d not in seen for e in entries for d in e['depends_on']):
        raise TrackerError('unknown task dependency')
    return {'adapter':'markdown','authority':'planning-source-observation','source_sha256':digest(text),'entries':entries}


def observe(text, adapter):
    if adapter == 'bmad-v6':
        return observe_v6(text)
    if adapter == 'markdown':
        return observe_markdown(text)
    raise TrackerError('bmad-v7 is a read-only documented preview; parser not implemented')


def propose(text, adapter, source_key, status, expected_sha256, evidence):
    """Return a patch for the tracker owner, never an accepted transition."""
    source = observe(text, adapter)
    if expected_sha256 != source['source_sha256']:
        raise TrackerError('stale source digest; re-observe before proposing')
    if not isinstance(evidence, dict) or set(evidence) != {'subject_sha','manifest','manifest_sha256'} or any(not isinstance(evidence.get(key), str) for key in ('subject_sha','manifest','manifest_sha256')) or not re.fullmatch(r'[0-9a-f]{40}', evidence.get('subject_sha','')) or not SHA.fullmatch(evidence.get('manifest_sha256','')):
        raise TrackerError('proposal requires subject-bound manifest references')
    path = Path(evidence['manifest'])
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise TrackerError('manifest reference must be contained and relative')
    matches = [e for e in source['entries'] if e['source_key'] == source_key and e['kind'] == 'story']
    if len(matches) != 1:
        raise TrackerError('target must identify exactly one story')
    entry = matches[0]
    if status not in ('in-progress','done') or (adapter == 'markdown' and status != 'done'):
        raise TrackerError('unsupported owner-mediated synchronization target')
    if entry['observed_status'] == 'done' and status != 'done':
        raise TrackerError('done entries never regress')
    rows = lines(text)
    changes = []
    def replace(line_number, new):
        old = rows[line_number-1]
        if old != new:
            changes.append({'line':line_number,'before':old,'after':new})
            rows[line_number-1] = new
    if adapter == 'markdown':
        replace(entry['line'], re.sub(r'^- \[[ xX]\]', '- [x]', rows[entry['line']-1]))
    else:
        def update(item, target):
            row = rows[item['line']-1]
            replace(item['line'], re.sub(r'(: +)'+re.escape(item['observed_status'])+r'(?=\s|$)', r'\g<1>'+target,row,count=1))
        update(entry,status)
        if status == 'in-progress':
            epic = 'epic-' + source_key.split('-')[0]
            parent = next((e for e in source['entries'] if e['source_key'] == epic),None)
            if parent is None:
                raise TrackerError('starting story requires explicit epic observation')
            if parent['observed_status'] == 'backlog':
                update(parent,'in-progress')
    return {'kind':'tracker-patch-proposal','owner':'bmad-workflow' if adapter == 'bmad-v6' else 'planning-owner',
            'applicability':'unverified-until-owner-checks-board-and-gate','source_sha256':expected_sha256,
            'proposed_sha256':digest(''.join(rows)),'evidence':evidence,'changes':changes}


def read(path):
    path = Path(path).absolute()
    fds = []
    try:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
        fds.append(fd)
        for part in path.parts[1:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fds.append(fd)
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        fds.append(leaf)
        before = os.fstat(leaf)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise TrackerError('tracker must be a bounded regular file')
        content = b''
        while len(content) <= MAX_BYTES:
            chunk = os.read(leaf, min(65536, MAX_BYTES + 1-len(content)))
            if not chunk:
                break
            content += chunk
        after = os.fstat(leaf)
        identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(content) > MAX_BYTES or identity(before) != identity(after) or identity(after) != identity(os.stat(path.name,dir_fd=fd,follow_symlinks=False)):
            raise TrackerError('tracker changed during read')
        for index, part in enumerate(path.parts[1:-1]):
            observed = os.stat(part, dir_fd=fds[index], follow_symlinks=False)
            opened = os.fstat(fds[index + 1])
            if (observed.st_dev, observed.st_ino) != (opened.st_dev, opened.st_ino):
                raise TrackerError('tracker ancestor changed during read')
        current_root = os.stat(path.anchor, follow_symlinks=False)
        opened_root = os.fstat(fds[0])
        if (current_root.st_dev, current_root.st_ino) != (opened_root.st_dev, opened_root.st_ino):
            raise TrackerError('tracker root changed during read')
        return content.decode('utf-8')
    except (OSError, UnicodeError):
        raise TrackerError('tracker unreadable or unsafe') from None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def detect(root, selected=None):
    """Detection checks two documented locations; never recursively crawls."""
    root = Path(root)
    found = [kind for kind, name in (('bmad-v6','sprint-status.yaml'),('bmad-v7','tickets.toml')) if (root/name).is_file()]
    if selected:
        if selected not in found:
            raise TrackerError('configured tracker not found')
        return selected
    if len(found) != 1:
        raise TrackerError('missing or mixed trackers require explicit configured choice')
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter',choices=['bmad-v6','markdown','bmad-v7'],required=True)
    parser.add_argument('--path',type=Path,required=True)
    args = parser.parse_args()
    try:
        result = observe(read(args.path),args.adapter)
    except TrackerError as exc:
        parser.exit(1,f'tracker: {exc}\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
