"""Presence, routing and argv rendering only; never launches an agent or probe."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path


def module(path, name):
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, Path(path).resolve())
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded
    finally:
        sys.dont_write_bytecode = previous


discovery = module(Path(__file__).absolute().parents[2] / 'sf-help/scripts/discover.py', 'sf_agents_discovery')
config = discovery.config
Error = discovery.SetupError
encoded = discovery.encoded
digest = discovery.digest


def load(root):
    reader = discovery.Reader(root)
    raw = reader.read(discovery.CONFIG)
    if raw is None:
        raise Error('configuration missing; run sf-help setup')
    data = config.validate_file(reader.root / discovery.CONFIG, root=reader.root)
    reader.finish()
    return reader, data


def presence(root, *, path=None, inventory=None):
    reader, data = load(root)
    inventory = inventory or {}
    if not isinstance(inventory, dict) or set(inventory) - set(data['agents']):
        raise Error('native inventory must name configured agents')
    observations = {}
    for name, agent in sorted(data['agents'].items()):
        detection = agent.get('detection', {'kind':'native-inventory'} if agent['kind'] == 'native'
                              else {'kind':'executable-presence','executable':Path(agent['invoke']['argv'][0]).name})
        kind = detection['kind']
        observed = None
        if kind == 'executable-presence':
            observed = shutil.which(detection['executable'], path=path) is not None
        elif kind == 'known-file':
            observed = reader.read(detection['path']) is not None
        elif name in inventory:
            if type(inventory[name]) is not bool:
                raise Error('native inventory values must be booleans from the host')
            observed = inventory[name]
        observations[name] = {'present':observed,'source':kind,'usable':'unverified',
                              'version':None,'auth':None,'effective_model':None}
    reader.finish()
    return {'schema':'sf-agent-presence/1','config_sha256':reader.sources[discovery.CONFIG],
            'root_identity':reader.identity,'agents':observations,'gh':{'present':shutil.which('gh', path=path) is not None,'auth':None},
            'native_fallback':data['routing']['fallback'],'sources':reader.sources}


def route(root, *, risk, complexity, operation, phase, observations, permissions=None, denied=False):
    reader, data = load(root)
    if type(risk) is not int or risk not in range(4) or complexity not in ('low','medium','high') or operation not in ('observe','write') or phase not in ('coding','review','analysis'):
        raise Error('invalid routing request')
    if (observations.get('schema') != 'sf-agent-presence/1'
            or observations.get('config_sha256') != reader.sources[discovery.CONFIG]
            or observations.get('root_identity') != reader.identity):
        raise Error('presence observations do not match current configuration')
    permissions = permissions or {}
    routing = data['routing']
    names = ([routing.get('complexity',{}).get(complexity),routing['coding']] if phase == 'coding'
             else [routing['independent_review']]) + [routing['fallback']]
    chain = list(dict.fromkeys(name for name in names if name))
    chain = chain[:chain.index(routing['fallback'])+1]
    result = {'schema':'sf-agent-route/1','chain':chain,'selected':None,'status':'blocked' if denied else 'unverified',
              'rationale':'permission denial stops the action; changing backend does not grant authority' if denied else '',
              'candidates':[],'requested_model':None,'effective_model':None,'permission_evidence':'unknown',
              'risk':risk,'complexity':complexity,'operation':operation,'phase':phase,
              'suggested_role':'sf-code-reviewer' if phase == 'review' else 'sf-principal-engineer' if risk >= 2 or complexity == 'high' else 'sf-engineer',
              'owner_checkpoint_required':risk == 3}
    for name in chain:
        agent = data['agents'][name]
        known = observations.get('agents',{}).get(name,{}).get('present')
        permission = permissions.get(name)
        if permission is not None and permission not in ('read-only','workspace-write'):
            raise Error('permission evidence must name observed supported restrictions')
        reason = None
        if denied:
            reason = 'action denied'
        elif risk not in agent['risk_tiers']:
            reason = 'risk tier unsupported'
        elif agent['kind'] == 'native' and known is False:
            reason = 'declared native capability unavailable'
        elif agent['kind'] == 'external' and known is not True:
            reason = 'external presence unavailable or unknown'
        elif agent['kind'] == 'external' and agent['invoke']['operation'] != operation:
            reason = 'recipe operation does not fit task'
        elif operation == 'observe' and permission != 'read-only':
            reason = 'enforced read-only permission unverified'
        elif operation == 'write' and permission != 'workspace-write':
            reason = 'write scope unverified'
        elif agent['kind'] == 'external' and weakening(agent['invoke']['argv']):
            reason = 'recipe requests permission weakening; host decision required'
        result['candidates'].append({'agent':name,'eligible':reason is None,'reason':reason})
        if result['selected'] is None and reason is None:
            result.update(selected=name,status='proposed',requested_model=agent.get('model_request'),
                          permission_evidence=permission,
                          rationale=f'{phase} / {complexity} / risk {risk}: first fitting configured candidate with observed permission scope; native fallback retained')
    if result['selected'] is None and not denied:
        result['rationale'] = 'no eligible observed scope; native worker remains fallback but permission or capability gap needs host reconciliation'
    reader.finish()
    return result


def weakening(argv):
    return any(token in ('--force','-f','--yolo','--trust','--approve-mcps','--dangerously-bypass-hook-trust')
               or token.startswith(('--force=','--approve-mcps=','--trust=')) for token in argv)


def invocation(root, name, values):
    _, data = load(root)
    if name not in data['agents']:
        raise Error('unknown configured agent')
    agent = data['agents'][name]
    if agent['kind'] == 'native':
        return {'status':'native','argv':None,'requested_model':agent.get('model_request'),'effective_model':None}
    recipe = agent['invoke']
    host = Path(recipe['argv'][0]).name
    tokens = recipe['argv']
    def option(flag):
        if any(t.startswith(flag+'=') for t in tokens) or tokens.count(flag) != 1 or tokens.index(flag)+1 >= len(tokens):
            return None
        return tokens[tokens.index(flag)+1]
    if host in ('codex','cursor-agent','agent'):
        protected = ('--sandbox','--cd','--workspace','--mode','--config','--profile')
        if (any(t.startswith(tuple(flag+'=' for flag in protected)) for t in tokens)
                or any(tokens.count(flag)>1 for flag in protected)
                or host == 'codex' and any(t == '--full-auto' or t.startswith(('-C','-s','-c','-p','--add-dir')) for t in tokens[1:])):
            raise Error('ambiguous or alternate scope options require recipe reconciliation')
    if host == 'codex':
        expected = 'read-only' if recipe['operation'] == 'observe' else 'workspace-write'
        if (len(tokens) < 2 or tokens[1] != 'exec' or option('--sandbox') != expected
                or option('--cd') != '{workspace}' or any(t in ('-c','--config','--profile','-p') or t.startswith(('--config=','--profile=')) for t in tokens)):
            raise Error('Codex recipe must preserve explicit operation sandbox and claimed workspace')
    if host in ('cursor-agent','agent') and (option('--workspace') != '{workspace}'
            or recipe['operation'] == 'observe' and option('--mode') not in ('ask','plan')
            or option('--sandbox') == 'disabled'):
        raise Error('Cursor recipe must preserve analysis mode and claimed workspace')
    if weakening(recipe['argv']):
        raise Error('permission-weakening recipe is not rendered as dispatch-ready')
    if set(values) - config.PLACEHOLDERS or any(not isinstance(v,str) or not v or v.startswith('-') or '\x00' in v or '\n' in v for v in values.values()):
        raise Error('invalid invocation substitutions')
    workspace = values.get('{workspace}')
    if workspace is None or Path(workspace).resolve() != Path(root).resolve():
        raise Error('workspace must be the verified claimed project directory')
    argv = []
    for token in recipe['argv']:
        if token in config.PLACEHOLDERS:
            if token not in values:
                raise Error('required whole-token substitution missing')
            argv.append(values[token])
        else:
            argv.append(token)
    cwd = (Path(root) / recipe['cwd']).resolve()
    if cwd != Path(root).resolve():
        raise Error('recipe cwd must be the claimed worktree root')
    return {'status':'rendered-unexecuted','argv':argv,'cwd':str(cwd),'operation':recipe['operation'],
            'env_references':recipe.get('env',{}),'requested_model':values.get('{model}',agent.get('model_request')),
            'effective_model':None,'authority':'host must verify claim, scope and current permission before dispatch'}


def parse_artifact(raw):
    """Strict bounded artifact JSON; config's smaller field limits do not apply."""
    if len(raw) > config.MAX_BYTES:
        raise Error('artifact exceeds 1MiB budget')
    def unique(pairs):
        value = {}
        for key,item in pairs:
            if key in value:
                raise Error('artifact contains duplicate object keys')
            value[key] = item
        return value
    def invalid_constant(value):
        raise Error('artifact contains a non-finite number')
    try:
        data = json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid_constant)
    except (ValueError,RecursionError) as exc:
        raise Error('artifact must be bounded strict UTF-8 JSON') from exc
    if not isinstance(data,dict):
        raise Error('artifact must be an object')
    pending, count = [(data,0)],0
    while pending:
        value,depth = pending.pop()
        count += 1
        if count > config.MAX_NODES or depth > config.MAX_DEPTH:
            raise Error('artifact exceeds depth or entry budget')
        if isinstance(value,str) and any((ord(c)<32 and c not in '\n\r\t') or 0xD800<=ord(c)<=0xDFFF for c in value):
            raise Error('artifact contains unsupported control or surrogate text')
        if isinstance(value,float) and not math.isfinite(value):
            raise Error('artifact contains a non-finite number')
        if isinstance(value,dict):
            for key,item in value.items():
                pending.extend(((key,depth+1),(item,depth+1)))
        elif isinstance(value,list):
            pending.extend((item,depth+1) for item in value)
    return data


def read_json(path):
    path = Path(path).absolute()
    raw = config.read_bytes(path.parent, path.name)
    return parse_artifact(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    sub = parser.add_subparsers(dest='command',required=True)
    detect = sub.add_parser('discover')
    detect.add_argument('--inventory',type=Path)
    render = sub.add_parser('render-invocation')
    render.add_argument('--agent',required=True)
    render.add_argument('--values',type=Path,required=True)
    routing = sub.add_parser('route')
    routing.add_argument('--request',type=Path,required=True)
    args = parser.parse_args()
    try:
        if args.command == 'discover':
            result = presence(args.project,inventory=read_json(args.inventory) if args.inventory else None)
        elif args.command == 'render-invocation':
            result = invocation(args.project,args.agent,read_json(args.values))
        else:
            result = route(args.project,**read_json(args.request))
        print(encoded(result).decode(),end='')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'agents: {exc if isinstance(exc,Error) else "invalid or unsafe input"}\n')


if __name__ == '__main__':
    main()
