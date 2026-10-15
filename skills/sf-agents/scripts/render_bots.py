"""Propose derived bot rules; apply an exact approved digest with retained recovery."""
from __future__ import annotations

import argparse
import difflib
import fcntl
import importlib.util
import os
import re
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

previous = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    spec = importlib.util.spec_from_file_location('sf_bot_agents', Path(__file__).with_name('agents.py'))
    agents = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agents)
finally:
    sys.dont_write_bytecode = previous
D = agents.discovery
Error = agents.Error
RECEIPT = '.software-factory/bot-receipt.json'
START, END = 'software-factory:principles:start', 'software-factory:principles:end'
TARGETS = {
    'greptile': {'.greptile/rules.md':'rules.md.tmpl','.greptile/config.json':'config.json.tmpl','.greptile/files.json':'files.json.tmpl'},
    'coderabbit': {'.coderabbit.yaml':'coderabbit.yaml.tmpl'},
    'bugbot': {'.cursor/BUGBOT.md':'BUGBOT.md.tmpl','.cursor/config/bugbot.yaml':'bugbot.yaml.tmpl'},
    'copilot': {'.github/copilot-instructions.md':'copilot-instructions.md.tmpl'},
}


def reference(value):
    if not isinstance(value,str) or not value.strip() or len(value) > 512 or not value.isprintable():
        raise Error('source-linked approval reference required; host verifies authority')
    if value == 'sf-setup-reuse/1':
        raise Error('setup reuse is not fresh principles approval')
    agents.config.inspect_strings(value)
    return value


def source_root():
    """Only canonical source layout may use top-level pack dependencies."""
    here = Path(__file__).resolve()
    root = here.parents[3]
    if (agents.config.schema_path().resolve() != root/'schemas/config.schema.json'
            or not (root/'install.py').is_file()
            or here != root/'skills/sf-agents/scripts/render_bots.py'):
        raise Error('installed dependency missing; restore the full project installation')
    return root


def asset(bot, name):
    here = Path(__file__).absolute()
    base = here.parents[1]/'templates'
    if not base.is_dir():
        base = source_root()/'integrations/bots'
    raw = agents.config.read_bytes(base, bot+'/'+name, required=False)
    if raw is not None:
        return raw.decode()
    raise Error('canonical bot templates missing; use full project installation')


def section(text, markdown):
    before = '<!-- '+START+' -->\n' if markdown else '# '+START+'\n'
    after = '<!-- '+END+' -->\n' if markdown else '# '+END+'\n'
    return before + text.rstrip('\n') + '\n' + after


def splice(old, generated, ownership, markdown):
    if old is None:
        return generated, None
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1:
            return None, 'ambiguous managed markers'
        start_marker = '<!-- '+START+' -->\n' if markdown else '# '+START+'\n'
        end_marker = '<!-- '+END+' -->\n' if markdown else '# '+END+'\n'
        start, end = old.find(start_marker), old.find(end_marker)
        if start < 0 or end < start:
            return None, 'malformed managed markers'
        end += len(end_marker)
        if ownership != D.digest(old[start:end].encode()):
            return None, 'managed content changed or lacks ownership receipt'
        if not markdown and (old[:start].strip() or old[end:].strip()):
            return None, 'unmanaged YAML surrounds managed section; review topology manually'
        return old[:start] + generated + old[end:], None
    if markdown:
        return old + ('\n' if old.endswith('\n') else '\n\n') + generated, None
    return None, 'structured user configuration preserved; review proposal manually'


def plan(root, selected, principles_ref):
    reader, data = agents.load(root)
    if not isinstance(selected,list) or len(selected) != len(set(selected)) or any(b not in TARGETS for b in selected):
        raise Error('select supported bot IDs once each')
    if not selected:
        return {'schema':'sf-bot-proposal/1','status':'not_applicable','files':{},'proposals':{}}
    reference(principles_ref)
    for bot in selected:
        entry = data.get('review_bots',{}).get(bot,{})
        if entry.get('enabled') is not True or entry.get('config') not in TARGETS[bot]:
            raise Error('selected bot must be explicitly configured with a supported target')
    sources, rule_parts = {}, []
    for name in ('product','conventions','risk','evals'):
        path = data['documents']['principles'][name]
        raw = reader.read(path)
        if not raw or not raw.strip():
            raise Error('all four approved principles modules must be nonempty')
        text = raw.decode()
        if START in text or END in text:
            raise Error('principles contain reserved managed marker')
        sources[path] = D.digest(raw)
        rule_parts.append(f'## {name}\nSource: {path}; SHA256: {sources[path]}\n\n{text.rstrip()}\n')
    rules = 'Generated from approved principles; do not hand-edit this section.\n\n'+'\n'.join(rule_parts)
    if len(rules) > 19000:
        raise Error('derived rules exceed supported instruction budget; propose a reviewed scoped split')
    prior_raw = reader.read(RECEIPT)
    prior = agents.config.parse(prior_raw.decode()) if prior_raw else {}
    owned = prior.get('sections',{}) if prior.get('schema') == 'sf-bot-receipt/1' else {}
    files, proposals, sections = {}, {}, {}
    for bot in sorted(selected):
        for target, filename in TARGETS[bot].items():
            template = asset(bot,filename)
            refs = {'files':[{'path':p,'description':'Approved principles; SHA256: '+h} for p,h in sources.items()]}
            content = template.replace('{{RULES}}',rules).replace('{{INDENTED_RULES}}','\n'.join('        '+line for line in rules.splitlines()))
            content = content.replace('{{FILES_JSON}}',D.encoded(refs).decode().rstrip())
            content = content.replace('{{CONFIG_JSON}}',D.encoded({'autoReview':[],'instructions':rules}).decode().rstrip())
            if '{{' in content:
                raise Error('unsupported template placeholder')
            raw = reader.read(target)
            old = None if raw is None else raw.decode()
            is_json = target.endswith('.json')
            generated = content if is_json else section(content,target.endswith('.md'))
            if is_json:
                okay = raw is None or (prior.get('files',{}).get(target) == D.digest(raw))
                updated, problem = (generated,None) if okay else (None,'structured user JSON preserved')
                if problem and target == '.greptile/config.json':
                    try:
                        value = agents.config.parse(old)
                        existing = value.get('instructions','')
                        if not isinstance(existing,str):
                            raise TypeError()
                        value['instructions'] = existing+'\n\n'+rules
                        generated = D.encoded(value).decode()
                    except (ValueError,TypeError):
                        pass
            else:
                updated, problem = splice(old,generated,owned.get(target),target.endswith('.md'))
            if problem:
                proposals[target] = {'reason':problem,'diff':''.join(difflib.unified_diff((old or '').splitlines(True),generated.splitlines(True),fromfile=target,tofile=target+'.proposed'))}
            elif updated != old:
                files[target] = updated
            if not problem and not is_json:
                sections[target] = D.digest(generated.encode())
    reader.finish()
    body = {'schema':'sf-bot-proposal/1','status':'proposed','root_identity':reader.identity,
            'selected':sorted(selected),'principles_ref':principles_ref,'principles':sources,
            'sources':reader.sources,'files':files,'proposals':proposals,'sections':sections}
    body['sha256'] = D.digest(D.encoded(body))
    return body


def read_at(fd, name):
    try:
        source = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(source,'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > agents.config.MAX_BYTES:
            raise Error('publication entry is not a bounded regular file')
        raw = stream.read(agents.config.MAX_BYTES+1)
        after = os.fstat(stream.fileno())
        current = os.stat(name,dir_fd=fd,follow_symlinks=False)
        identity = lambda x: (x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if len(raw)>agents.config.MAX_BYTES or identity(before)!=identity(after) or identity(after)!=identity(current):
            raise Error('publication entry changed')
        return raw


@contextmanager
def parent(root, identity, relative, create=False):
    parts = D.safe_path(relative).parts
    fds = [os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)]
    try:
        def check():
            current = os.stat(root,follow_symlinks=False)
            opened = os.fstat(fds[0])
            if [current.st_dev,current.st_ino] != identity or [opened.st_dev,opened.st_ino] != identity:
                raise Error('approved root replaced')
            for index,part in enumerate(parts[:len(fds)-1]):
                current,opened = os.stat(part,dir_fd=fds[index],follow_symlinks=False),os.fstat(fds[index+1])
                if (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino):
                    raise Error('publication ancestor replaced')
        check()
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part,0o755,dir_fd=fds[-1])
                except FileExistsError:
                    pass
            fds.append(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fds[-1]))
            check()
        yield fds[-1],parts[-1],check
        check()
    finally:
        for fd in reversed(fds):
            os.close(fd)


def lifecycle():
    here = Path(__file__).absolute()
    path = here.with_name('install_lifecycle.py')
    if not path.exists():
        path = source_root()/'scripts/install_lifecycle.py'
    helper = agents.module(path,'sf_bot_publication')
    helper.read_at = read_at  # Bounded capture verification, including contested files.
    return helper


def verify(root, proposal, published):
    reader = D.Reader(root)
    if reader.identity != proposal['root_identity']:
        raise Error('approved root replaced')
    for path, expected in proposal['sources'].items():
        raw = reader.read(path)
        wanted = D.digest(published[path]) if path in published else expected
        if (None if raw is None else D.digest(raw)) != wanted:
            raise Error('proposal stale; source or target changed')
    reader.finish()


def apply(root, proposal, approved_sha, decision):
    reference(decision)
    if proposal.get('status') == 'not_applicable':
        raise Error('no selected bot changes to approve')
    fresh = plan(root,proposal.get('selected'),proposal.get('principles_ref'))
    if not re.fullmatch(r'[a-f0-9]{64}',approved_sha or '') or fresh != proposal or fresh['sha256'] != approved_sha:
        raise Error('approval must bind the exact current proposal digest')
    if not proposal['files']:
        return {'status':'proposal-only' if proposal['proposals'] else 'unchanged','written':[],'proposals':proposal['proposals']}
    helper = lifecycle()
    root = Path(root).resolve()
    identity = proposal['root_identity']
    verify(root,proposal,{})  # No lock, backup or directory writes on preflight refusal.
    with parent(root,identity,'.software-factory/.install.lock') as (lock_parent,name,check):
        lock = os.open(name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=lock_parent)
        try:
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise Error('unsafe shared installation lock')
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise Error('installation lock busy; retry after owner finishes') from None
            check()
            verify(root,proposal,{})
            prior_raw = D.Reader(root).read(RECEIPT)
            prior = agents.config.parse(prior_raw.decode()) if prior_raw else {}
            receipt = {'schema':'sf-bot-receipt/1','proposal_sha256':approved_sha,'approval_ref':decision,
                       'principles_ref':proposal['principles_ref'],'principles':proposal['principles'],
                       'files':{**prior.get('files',{}),**{p:D.digest(v.encode()) for p,v in proposal['files'].items()}},
                       'sections':{**prior.get('sections',{}),**proposal['sections']}}
            pending = {p:v.encode() for p,v in proposal['files'].items()}
            pending[RECEIPT] = D.encoded(receipt)
            root_fd = os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                quarantine, recovery = helper.recovery_directory(root_fd)
            finally:
                os.close(root_fd)
            written, originals = {}, {}
            try:
                for relative, content in pending.items():
                    verify(root,proposal,written)
                    with parent(root,identity,relative,create=True) as (fd,name,check):
                        expected = read_at(fd,name)
                        wanted = proposal['sources'].get(relative)
                        if (None if expected is None else D.digest(expected)) != wanted:
                            raise Error('publication target changed')
                        check()
                        helper.publish(fd,name,content,expected=expected,quarantine=quarantine,relative=relative)
                        written[relative], originals[relative] = content,expected
                verify(root,proposal,written)
            except BaseException as exc:
                contested = []
                for relative,content in reversed(list(written.items())):
                    try:
                        with parent(root,identity,relative) as (fd,name,check):
                            if read_at(fd,name) != content:
                                contested.append(relative)
                                continue
                            check()
                            helper.publish(fd,name,originals[relative],expected=content,quarantine=quarantine,relative=relative)
                    except (OSError,ValueError):
                        contested.append(relative)
                raise Error('apply interrupted; reconcile retained recovery copies at '+recovery+'; contested paths: '+(', '.join(contested) or 'none')) from exc
            finally:
                os.close(quarantine)
            return {'status':'applied','written':list(written),'recovery':recovery,'proposals':proposal['proposals']}
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN)
            os.close(lock)  # Persistent shared inode: never unlink a flock file.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    sub = parser.add_subparsers(dest='command',required=True)
    prepare = sub.add_parser('plan')
    prepare.add_argument('--bots',nargs='*',default=[])
    prepare.add_argument('--principles-ref')
    execute = sub.add_parser('apply')
    execute.add_argument('--proposal',type=Path,required=True)
    execute.add_argument('--approved-sha',required=True)
    execute.add_argument('--decision',required=True)
    args = parser.parse_args()
    try:
        result = (plan(args.project,args.bots,args.principles_ref) if args.command == 'plan' else
                  apply(args.project,agents.read_json(args.proposal),args.approved_sha,args.decision))
        print(D.encoded(result).decode(),end='')
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.exit(1,f'bots: {exc if isinstance(exc,Error) else "invalid or unsafe input"}\n')


if __name__ == '__main__':
    main()
