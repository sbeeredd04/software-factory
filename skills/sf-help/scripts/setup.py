"""Prepare setup without writes; apply only an explicitly approved proposal digest.

Creates missing setup files only. Existing bytes are never overwritten. Approval
references are provenance supplied by the host, not authentication by this CLI.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import secrets
import sys
from pathlib import Path

previous = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    spec = importlib.util.spec_from_file_location('sf_setup_discover',Path(__file__).with_name('discover.py'))
    discover = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discover)
finally:
    sys.dont_write_bytecode = previous
config = discover.config
Error = discover.SetupError
HOME = '.software-factory/context/'
OUTPUTS = {discover.CONFIG, HOME+'ARCHITECTURE.md', HOME+'CONVENTIONS.md', HOME+'TASKS.md', HOME+'evals-draft.json', *(HOME+'principles/'+name+'.md' for name in ('product','conventions','risk','evals'))}


def catalog():
    text = (Path(__file__).absolute().parents[1]/'references/questions.md').read_text()
    rows = []
    group = None
    current = None
    for line in text.splitlines():
        if line.startswith('## Group '):
            group = line[9]
        if match := re.fullmatch(r'### Q([0-9]{2}) — (.+)',line):
            current = {'id':int(match[1]),'group':group,'question':match[2]}
            rows.append(current)
        elif current:
            for name in ('Why','Default','Keys'):
                if line.startswith(name+': '):
                    current[name.lower()] = line[len(name)+2:]
    if [r['id'] for r in rows] != list(range(1,21)) or any(not all(k in r for k in ('why','default','keys')) for r in rows):
        raise Error('shipped question catalog is incomplete')
    return rows


def template(name):
    here = Path(__file__).absolute()
    for directory in (here.parents[1]/'templates',here.parents[3]/'templates'):
        if directory.is_dir():
            return config.read_bytes(directory,name).decode()
    raise Error('canonical templates missing; use the project installer for full setup')


def default_config(documents):
    return {'version':1,'project':{'name':'Project','root':'..','repositories':{'app':{'path':'.'}}},
            'documents':documents,'tracker':{'adapter':'markdown','path':HOME+'TASKS.md'},
            'board':{'dir':HOME+'board','regenerate':'on-write'},'planning':{'depth':'adaptive'},
            'branches':{'integration':'dev','protected':['main'],'story_prefix':'story/','merge_method':'merge','direct_push':False},
            'agents':{'native':{'kind':'native','description':'Current host; effective capacity and model remain observed facts','risk_tiers':[0,1,2,3],'detection':{'kind':'native-inventory'}}},
            'routing':{'coding':'native','independent_review':'native','fallback':'native'},
            'environments':{},'review_bots':{},'verification':{'required_checks':['qa','evals','code_review','ci','review_bots']},
            'autonomy':{'local_edits':True,'commits':False,'push':False,'open_pr':False,'merge_integration':False,'deploy':False,'standing_delegations':[],'blocked_behavior':'continue-independent'},
            'checkpoints':{'transitions':['epic-acceptance'],'manual':True,'before_reset':True,'before_external_write':True,'retro_cadence':'epic'},
            'budgets':{'mode':'alarm','stall_repetitions':3},'reporting':{'style':'concise-evidence'},
            'context':{'retention':documents['principles']['risk'],'redaction':documents['principles']['risk']},
            'bmad':{'install_version':'6.12.0','modules':['core','bmm','bmb','cis','tea'],'custom_root':'_bmad/custom','automatic_updates':False},
            'extensions':{'skills':[],'mcp':[],'overlays':[]},
            'operations':{'enabled':False,'sources':[],'followup':'propose-bug','notifications':'meaningful-changes'}}


class View:
    def __init__(self, reader, files, relative=None):
        self.reader, self.files, self.relative = reader,files,relative

    def __truediv__(self, relative):
        return View(self.reader,self.files,relative)

    def read_bytes(self):
        discover.safe_path(self.relative)
        if self.relative in self.files:
            return self.files[self.relative].encode()
        return self.reader.read(self.relative)


def validate_answers(answers):
    if not isinstance(answers,list) or len(answers) != 20 or [a.get('id') if isinstance(a,dict) else None for a in answers] != list(range(1,21)):
        raise Error('receipt requires exactly twenty ordered answer slots')
    for answer in answers:
        if set(answer) != {'id','state','value','source'} or answer['state'] not in ('confirmed','defaulted','unknown') or not isinstance(answer['value'],str) or len(answer['value']) > 2048 or not isinstance(answer['source'],str) or len(answer['source']) > 512:
            raise Error('invalid bounded answer record')
        if answer['state'] == 'confirmed' and not answer['source'].strip():
            raise Error('confirmed answers need source references')
    config.bounded(answers)
    config.inspect_strings(answers)


def validate_candidate(reader, files, data):
    config.validate_data(data,View(reader,files))
    if data['project']['root'] != '..':
        raise Error('setup uses the conventional config-relative project root')
    if discover.CONFIG in files and data.get('operations',{}).get('enabled'):
        raise Error('initial setup keeps monitoring disabled; review source access and authority separately')


def prefilled_answers(data, observation):
    unknown = {2,3,6,7,9,10,11,14,19}
    observed = {6:observation['capabilities'],8:observation['commands'],9:observation['ci'],
                10:observation['binaries'],11:observation['bots'],14:observation['documents'],19:observation['bmad']}
    answers = []
    for row in catalog():
        configured = {}
        for key in row['keys'].split(', '):
            current = data
            for segment in key.split('.'):
                current = current.get(segment) if isinstance(current,dict) else None
            configured[key] = current
        context = discover.encoded({'configured':configured,'observation':observed.get(row['id'],'not independently verified')}).decode().strip()
        value = row['default']+'\n'+context
        if len(value) > 2048:
            value = value[:1990]+'\n[summary truncated; review full proposal]'
        answers.append({'id':row['id'],'state':'unknown' if row['id'] in unknown else 'defaulted',
                        'value':value,'source':'proposal:config; discovery:'+discover.CRAWL})
    return answers


def propose(root, answers=None, draft=None, draft_documents=None):
    if draft is not None:
        config.validate_schema(draft,config.load(config.schema_path()))
    observation = discover.discover(root)
    if not observation['greenfield'] and observation['crawl']['status'] != 'observed' and not observation['config_present']:
        raise Error('existing repository needs the sf-crawl artifact first; discovery does not recrawl')
    reader = discover.Reader(root)
    if reader.identity != observation['root_identity']:
        raise Error('project changed after discovery')
    for relative,expected in observation['sources'].items():
        reader.read(relative)
        if reader.sources[relative] != expected:
            raise Error('source changed after discovery; repeat discovery')
    for relative,expected in observation['directories'].items():
        reader.names(relative)
        if reader.directories[relative] != expected:
            raise Error('directory changed after discovery; repeat discovery')
    files = {}
    def missing(relative, content):
        if reader.read(relative) is None:
            files[relative] = content
        return relative
    document_paths = {'principles':{}}
    for name in ('product','conventions','risk','evals'):
        relative = HOME+'principles/'+name+'.md'
        body = template('PRINCIPLES.md')+'\n## '+name.title()+' setup draft\n\nUnknown project decisions require confirmation. Source: '+discover.CRAWL+'.\n'
        if name == 'evals':
            body += '\nThe eval plan is a draft; no signoff, coverage or execution is established.\n'
        document_paths['principles'][name] = missing(relative,body)
    for key, filename in (('architecture','ARCHITECTURE.md'),('conventions','CONVENTIONS.md')):
        # Existing conventional documents remain authoritative and byte-identical.
        document_paths[key] = filename if reader.read(filename) is not None else missing(HOME+filename,template(filename))
    document_paths['extra_context'] = observation['documents']
    missing(HOME+'TASKS.md','# Planning candidates\n\nNo accepted delivery stories yet. Ground intent and acceptance before GO.\n')
    missing(HOME+'evals-draft.json',discover.encoded({'status':'draft','surfaces':[],'cases':[],'outstanding':['Confirm intended behavior, failure cases, real commands and owner signoff.']}).decode())
    original = reader.read(discover.CONFIG)
    if original is not None:
        data = config.parse(original.decode())
        if draft is not None and discover.encoded(data) != discover.encoded(draft):
            raise Error('existing config differs; preserve it and review a separate amendment')
        # Existing projects receive no unrelated generated documents.
        files = {}
    else:
        data = draft if draft is not None else default_config(document_paths)
        files[discover.CONFIG] = discover.encoded(data).decode()
        if draft is not None:
            documents = data.get('documents',{})
            references = set(documents.get('principles',{}).values())
            references.update(documents.get('extra_context',[]))
            references.update(documents.get(key) for key in ('architecture','conventions'))
            references.add(data.get('tracker',{}).get('path'))
            # The chosen config owns its sources; omit competing scaffolds.
            files = {path:body for path,body in files.items() if path == discover.CONFIG or path in references}
    if draft_documents is not None:
        if not isinstance(draft_documents,dict) or any(path not in files or not path.endswith('.md') or not isinstance(body,str) for path,body in draft_documents.items()):
            raise Error('document drafts may replace only proposed missing Markdown files')
        files.update(draft_documents)
    validate_candidate(reader,files,data)
    old_receipt = reader.read(discover.RECEIPT)
    if old_receipt is not None:
        receipt = config.parse(old_receipt.decode())
        validate_answers(receipt.get('answers'))
        if receipt.get('config_sha256') != discover.digest(original or files[discover.CONFIG].encode()):
            raise Error('setup receipt no longer matches config; review an amendment, preserve prior evidence')
        if answers is not None and answers != receipt['answers']:
            raise Error('confirmed setup history is immutable; review an explicit amendment')
        reader.finish()
        return {'schema':'sf-setup-reuse/1','changes':[], 'answers':receipt['answers'],'receipt':discover.RECEIPT,
                'config_sha256':receipt['config_sha256'],'discovery':observation,
                'provenance':'prior answers preserved; current authority and approval freshness not established'}
    if answers is None:
        answers = prefilled_answers(data,observation)
    validate_answers(answers)
    reader.finish()
    reader.check_root()
    proposal = {'schema':'sf-setup-proposal/1','root_identity':reader.identity,
                'sources':reader.sources,'discovery':observation,'files':files,'config':data,'answers':answers,
                'outstanding':[a['id'] for a in answers if a['state']=='unknown'],
                'first_lap':{'kind':'proposal','recommendation':'scratch-clone dry run before an unfamiliar delivery lap', 'scope':'Build one minimal behavior with one meaningful test and independent review; confirm the actual user outcome before GO.'}}
    config.bounded(proposal)
    config.inspect_strings(proposal)
    proposal['sha256'] = discover.digest(discover.encoded(proposal))
    return proposal


def check_proposal(proposal, root, approved_sha, decision):
    if not isinstance(proposal,dict) or set(proposal) != {'schema','root_identity','sources','discovery','files','config','answers','outstanding','first_lap','sha256'} or proposal['schema'] != 'sf-setup-proposal/1':
        raise Error('unsupported or incomplete proposal')
    config.bounded(proposal)
    unsigned = {k:v for k,v in proposal.items() if k != 'sha256'}
    if not re.fullmatch(r'[0-9a-f]{64}',approved_sha or '') or approved_sha != proposal['sha256'] or approved_sha != discover.digest(discover.encoded(unsigned)):
        raise Error('approval must name the exact reviewed proposal digest')
    if not isinstance(decision,str) or not decision.strip() or len(decision) > 512:
        raise Error('source-linked approval reference required; host verifies owner authority')
    config.inspect_strings(decision)
    reader = discover.Reader(root)
    if proposal['root_identity'] != reader.identity:
        raise Error('proposal belongs to a different project directory')
    files = proposal['files']
    if not isinstance(files,dict) or not set(files) <= OUTPUTS or any(not isinstance(v,str) for v in files.values()):
        raise Error('proposal output outside setup scope')
    for path, content in files.items():
        discover.safe_path(path)
        if len(content.encode()) > config.MAX_BYTES:
            raise Error('setup file exceeds byte budget')
    validate_answers(proposal['answers'])
    if proposal['outstanding'] != [a['id'] for a in proposal['answers'] if a['state']=='unknown']:
        raise Error('outstanding questions differ from answer states')
    validate_candidate(reader,files,proposal['config'])
    actual = files[discover.CONFIG].encode() if discover.CONFIG in files else reader.read(discover.CONFIG)
    if actual is None:
        raise Error('preserved config is missing')
    actual_data = config.parse(actual.decode())
    validate_candidate(reader,files,actual_data)
    if discover.encoded(actual_data) != discover.encoded(proposal['config']):
        raise Error('actual config bytes differ from reviewed candidate')
    sources = proposal['sources']
    if not isinstance(sources,dict) or len(sources) > discover.MAX_FILES or not set(files) <= set(sources) or discover.RECEIPT not in sources or discover.CONFIG not in sources:
        raise Error('proposal lacks source preconditions')
    receipt = {'schema':'sf-setup-receipt/1','proposal_sha256':approved_sha,'approval_ref':decision,
               'config_path':discover.CONFIG,'config_sha256':discover.digest(files[discover.CONFIG].encode()) if discover.CONFIG in files else sources[discover.CONFIG],
               'answers':proposal['answers'],'outstanding':proposal['outstanding'],'discovery_sources':proposal['discovery']['sources'],
               'written':{path:discover.digest(content.encode()) for path,content in files.items()}}
    return reader, files, receipt


def verify_state(root, proposal, pending, written):
    """Recheck approved inputs, allowing only exact setup-owned publications."""
    reader = discover.Reader(root)
    if reader.identity != proposal['root_identity']:
        raise Error('approved project root was replaced')
    for path, expected in proposal['sources'].items():
        raw = reader.read(path)
        wanted = discover.digest(pending[path].encode()) if path in written else expected
        if (None if raw is None else discover.digest(raw)) != wanted:
            raise Error('approved proposal is stale; source changed')
    inventories = proposal['discovery']['directory_entries']
    fingerprints = proposal['discovery']['directories']
    if not isinstance(inventories,dict) or set(inventories) != set(fingerprints):
        raise Error('incomplete discovery inventory')
    for relative, entries in inventories.items():
        if entries is not None and (not isinstance(entries,list) or len(entries)>discover.MAX_FILES or any(not isinstance(e,str) or not re.fullmatch(r'[0-9a-f]{64}',e) for e in entries) or entries != sorted(set(entries))):
            raise Error('invalid bounded discovery inventory')
        original = None if entries is None else discover.digest(discover.encoded(entries))
        if fingerprints[relative] != original:
            raise Error('inventory digest mismatch')
        expected_entries = set(entries or [])
        base = Path(relative).parts
        for published in written:
            parts = Path(published).parts
            if parts[:len(base)] == base and len(parts)>len(base):
                expected_entries.add(discover.digest(parts[len(base)].encode()))
        expected = None if entries is None and not expected_entries else discover.digest(discover.encoded(sorted(expected_entries)))
        reader.names(relative)
        if reader.directories[relative] != expected:
            raise Error('approved proposal is stale; discovery directory changed')
    reader.finish()


def apply(root, proposal, approved_sha, decision):
    reader,files,receipt = check_proposal(proposal,root,approved_sha,decision)
    existing_receipt = reader.read(discover.RECEIPT)
    expected_receipt = discover.encoded(receipt)
    pending = {**files,discover.RECEIPT:expected_receipt.decode()}
    present = {path:reader.read(path) for path in files}
    if existing_receipt == expected_receipt and all(present[p] == content.encode() for p,content in files.items()):
        verify_state(root,proposal,pending,list(pending))
        return {'status':'unchanged','written':[], 'receipt':discover.RECEIPT}
    if existing_receipt is not None or any(raw is not None for raw in present.values()):
        raise Error('collision or partial prior setup; preserve files and reconcile before a fresh proposal')
    verify_state(root,proposal,pending,[])
    # Receipt is last; every publication and final outcome rechecks the inputs.
    written = []
    try:
        for relative,content in pending.items():
            verify_state(root,proposal,pending,written)
            publish(reader.root,relative,content.encode(),proposal['root_identity'])
            written.append(relative)
        verify_state(root,proposal,pending,written)
    except (OSError,Error):
        raise Error('setup apply incomplete or changed concurrently; preserve partial files and reconcile; completed paths: '+', '.join(written)) from None
    return {'status':'applied','written':written,'receipt':discover.RECEIPT}


def publish(root, relative, content, approved_identity):
    path = discover.safe_path(relative)
    fds = []
    temp = None
    try:
        fd = os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        fds.append(fd)
        opened_root = os.fstat(fd)
        if [opened_root.st_dev,opened_root.st_ino] != approved_identity:
            raise Error('publication target is not the approved root')
        def root_check():
            current = os.stat(root,follow_symlinks=False)
            if [current.st_dev,current.st_ino] != approved_identity:
                raise Error('approved root changed during publication')
        root_check()
        for part in path.parts[:-1]:
            root_check()
            try:
                os.mkdir(part,mode=0o755,dir_fd=fd)
            except FileExistsError:
                pass
            fd = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            fds.append(fd)
        def check():
            current = os.stat(root,follow_symlinks=False)
            opened = os.fstat(fds[0])
            if (current.st_dev,current.st_ino) != (opened.st_dev,opened.st_ino):
                raise Error('project root changed during apply')
            for index,part in enumerate(path.parts[:-1]):
                current = os.stat(part,dir_fd=fds[index],follow_symlinks=False)
                opened = os.fstat(fds[index+1])
                if (current.st_dev,current.st_ino) != (opened.st_dev,opened.st_ino):
                    raise Error('output ancestor changed during apply')
        check()
        temp = '.sf-setup-'+secrets.token_hex(8)+'.tmp'
        out = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(out,'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        check()
        os.link(temp,path.name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        check()
    finally:
        if temp is not None:
            try:
                os.unlink(temp,dir_fd=fds[-1])
            except FileNotFoundError:
                pass
        for fd in reversed(fds):
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['propose','apply'])
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--answers',type=Path)
    parser.add_argument('--config-draft',type=Path)
    parser.add_argument('--document-drafts',type=Path)
    parser.add_argument('--proposal',type=Path)
    parser.add_argument('--approve-sha')
    parser.add_argument('--decision-ref')
    args = parser.parse_args()
    try:
        if args.command == 'propose':
            answers = config.load(args.answers).get('answers') if args.answers else None
            result = propose(args.project,answers,config.load(args.config_draft) if args.config_draft else None,
                             config.load(args.document_drafts).get('files') if args.document_drafts else None)
        else:
            if not args.proposal:
                raise Error('apply requires reviewed proposal')
            result = apply(args.project,config.load(args.proposal),args.approve_sha,args.decision_ref)
        print(discover.encoded(result).decode(),end='')
    except (Error,config.ConfigError,OSError,ValueError,TypeError,KeyError) as exc:
        parser.exit(1,'setup: '+(str(exc) if isinstance(exc,(Error,config.ConfigError)) else 'invalid or unsafe setup input')+'\n')


if __name__ == '__main__':
    main()
