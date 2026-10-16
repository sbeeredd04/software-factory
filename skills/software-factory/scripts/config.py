"""Offline, read-only JSON-compatible YAML configuration validation.

parse/load check syntax only. validate_data checks the documented schema subset
and policy references; validate_file also establishes the config-relative root.
No commands in configuration are executed. See references/config-schema.md.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 20000
KEYWORDS = {'$schema', '$id', '$defs', 'title', 'description', 'type', 'required',
            'properties', 'additionalProperties', 'patternProperties', 'items',
            'enum', 'const', 'oneOf', 'minLength', 'maxLength', 'pattern', 'minimum',
            'maximum', '$ref', 'minItems', 'maxItems', 'uniqueItems'}
PLACEHOLDERS = {'{workspace}', '{task_file}', '{output_file}', '{model}', '{branch}'}
BYPASS = re.compile(r'(?:--(?:yolo|trust|dangerously-skip-permissions|dangerously-bypass-approvals-and-sandbox)(?:\b|=)|danger-full-access|bypassPermissions)')


class ConfigError(ValueError):
    """A bounded diagnostic that never includes input values."""


def fail(path, reason):
    # Keys are untrusted too: diagnostic paths are bounded and scrubbed.
    path = re.sub(r'[^A-Za-z0-9_.$\[\]-]', '?', path)[:180]
    raise ConfigError(f'{path}: {reason}')


def bounded(data, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > MAX_DEPTH or counter[0] > MAX_NODES:
        fail('$', 'document exceeds depth or entry budget')
    if isinstance(data, str) and (len(data) > 16384 or any((ord(c) < 32 and c not in '\n\r\t') or 0xD800 <= ord(c) <= 0xDFFF for c in data)):
        fail('$', 'string exceeds budget or contains control characters')
    if isinstance(data, float) and not math.isfinite(data):
        fail('$', 'non-finite numbers are unsupported')
    if isinstance(data, (dict, list)):
        for key, value in (data.items() if isinstance(data, dict) else enumerate(data)):
            if isinstance(data, dict):
                if not isinstance(key, str) or len(key) > 128:
                    fail('$', 'object key exceeds budget or is not a string')
                bounded(key, depth + 1, counter)
            bounded(value, depth + 1, counter)


def parse(text):
    """Strict syntax parsing only; incomplete objects remain parseable."""
    if len(text.encode('utf-8')) > MAX_BYTES:
        fail('$', 'configuration exceeds byte budget')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail('$', 'duplicate object key')
            result[key] = value
        return result
    try:
        data = json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda _: fail('$', 'non-finite number'))
    except json.JSONDecodeError as exc:
        fail('$', f'JSON-compatible YAML subset requires JSON syntax (line {exc.lineno}, column {exc.colno})')
    except RecursionError:
        fail('$', 'document exceeds depth budget')
    except ValueError as exc:
        if isinstance(exc, ConfigError):
            raise
        fail('$', 'JSON-compatible YAML subset value exceeds parser bounds')
    if not isinstance(data, dict):
        fail('$', 'configuration must be an object in the JSON-compatible YAML subset')
    bounded(data)
    return data


def read_bytes(root, relative, *, required=True):
    """Descriptor-relative regular-file read; symlinks and special files fail.

    No filesystem writes. Already-open ancestors keep replacements from redirecting
    the read outside the declared root. The leaf identity/size/mtime is rechecked.
    """
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        fail('$path', 'path must be contained and relative')
    descriptors = []
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in p.parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        leaf = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(leaf)
        before = os.fstat(leaf)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            fail('$path', 'expected a regular file within byte budget')
        content = bytearray()
        while len(content) <= MAX_BYTES:
            chunk = os.read(leaf, min(65536, MAX_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(leaf)
        current = os.stat(p.name, dir_fd=fd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(content) > MAX_BYTES or identity(before) != identity(after) or identity(after) != identity(current):
            fail('$path', 'source changed during bounded read')
        for index, part in enumerate(p.parts[:-1]):
            observed = os.stat(part, dir_fd=descriptors[index], follow_symlinks=False)
            opened = os.fstat(descriptors[index + 1])
            if (observed.st_dev, observed.st_ino) != (opened.st_dev, opened.st_ino):
                fail('$path', 'source ancestor changed during read')
        current_root = os.stat(root, follow_symlinks=False)
        opened_root = os.fstat(descriptors[0])
        if (current_root.st_dev, current_root.st_ino) != (opened_root.st_dev, opened_root.st_ino):
            fail('$path', 'source root changed during read')
        return bytes(content)
    except FileNotFoundError:
        if required:
            fail('$path', 'referenced file is missing or unreadable')
        return None
    except OSError:
        fail('$path', 'referenced file is unreadable, a symlink, or unsafe')
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def load(path):
    path = Path(path).absolute()
    try:
        return parse(read_bytes(Path(path.anchor), path.relative_to(path.anchor)).decode('utf-8'))
    except UnicodeDecodeError:
        fail('$', 'configuration file is not UTF-8 text')


def schema_path():
    here = Path(__file__).absolute()
    candidates = [here.with_name('config.schema.json'), here.parent.parent / 'schemas/config.schema.json',
                  here.parents[3] / 'schemas/config.schema.json']
    for path in candidates:
        if path.is_file():
            return path
    fail('$schema', 'shipped config.schema.json is missing')


def check_schema(schema):
    """Refuse unsupported keywords even in unused branches; local refs only."""
    bounded(schema)
    visits = [0]
    def visit(node, stack=()):
        visits[0] += 1
        if visits[0] > MAX_NODES or len(stack) > MAX_DEPTH:
            fail('$schema', 'schema expansion exceeds budget')
        if not isinstance(node, dict):
            fail('$schema', 'schema nodes must be objects')
        if set(node) - KEYWORDS:
            fail('$schema', 'unsupported schema keyword')
        if 'type' in node:
            kinds = node['type'] if isinstance(node['type'], list) else [node['type']]
            if not kinds or any(not isinstance(k, str) or k not in ('object', 'array', 'string', 'boolean', 'integer', 'number', 'null') for k in kinds):
                fail('$schema', 'unsupported schema type')
        for field in ('$defs', 'properties', 'patternProperties'):
            if field in node and not isinstance(node[field], dict):
                fail('$schema', 'schema property maps must be objects')
        for field in ('required', 'enum', 'oneOf'):
            if field in node and not isinstance(node[field], list):
                fail('$schema', 'schema collection must be an array')
        if 'required' in node and any(not isinstance(k, str) for k in node['required']):
            fail('$schema', 'required names must be strings')
        if 'additionalProperties' in node and not isinstance(node['additionalProperties'], (bool, dict)):
            fail('$schema', 'additionalProperties must be boolean or schema')
        for field in ('minLength', 'maxLength', 'minItems', 'maxItems'):
            if field in node and (type(node[field]) is not int or node[field] < 0):
                fail('$schema', 'schema size bounds must be nonnegative integers')
        for field in ('minimum', 'maximum'):
            if field in node and type(node[field]) not in (int, float):
                fail('$schema', 'numeric bounds must be numbers')
        if 'uniqueItems' in node and type(node['uniqueItems']) is not bool:
            fail('$schema', 'uniqueItems must be boolean')
        if '$ref' in node:
            ref = node['$ref']
            if not isinstance(ref, str) or not re.fullmatch(r'#/\$defs/[A-Za-z0-9_-]+', ref):
                fail('$schema', 'only local definition references are supported')
            if ref in stack:
                fail('$schema', 'recursive schema reference')
            target = schema.get('$defs', {}).get(ref.split('/')[-1])
            if target is None:
                fail('$schema', 'missing local definition')
            visit(target, (*stack, ref))
        for key in ('$defs', 'properties', 'patternProperties'):
            for name, child in node.get(key, {}).items():
                if key == 'patternProperties':
                    try:
                        re.compile(name)
                    except re.error:
                        fail('$schema', 'invalid property pattern')
                visit(child, stack)
        if 'items' in node:
            visit(node['items'], stack)
        if isinstance(node.get('additionalProperties'), dict):
            visit(node['additionalProperties'], stack)
        for child in node.get('oneOf', []):
            visit(child, stack)
        if 'pattern' in node:
            try:
                re.compile(node['pattern'])
            except re.error:
                fail('$schema', 'invalid string pattern')
    visit(schema)


def validate_schema(data, schema):
    check_schema(schema)
    types = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
             'string': lambda x: isinstance(x, str), 'boolean': lambda x: type(x) is bool,
             'integer': lambda x: type(x) is int or (type(x) is float and x.is_integer()),
             'number': lambda x: type(x) in (int, float), 'null': lambda x: x is None}
    def equal(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if isinstance(a, dict) or isinstance(b, dict):
            return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
        if isinstance(a, list) or isinstance(b, list):
            return isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
        return a == b
    def visit(value, node, path):
        if '$ref' in node:
            visit(value, schema['$defs'][node['$ref'].split('/')[-1]], path)
        if 'oneOf' in node:
            matches = 0
            for branch in node['oneOf']:
                try:
                    visit(value, branch, path)
                    matches += 1
                except ConfigError:
                    pass
            if matches != 1:
                fail(path, 'must match exactly one supported variant')
        if 'type' in node:
            names = node['type'] if isinstance(node['type'], list) else [node['type']]
            if any(t not in types for t in names):
                fail('$schema', 'unknown schema type')
            if not any(types[t](value) for t in names):
                fail(path, 'unexpected value type')
        if 'const' in node and not equal(value, node['const']):
            fail(path, 'unexpected constant')
        if 'enum' in node and not any(equal(value, x) for x in node['enum']):
            fail(path, 'value outside supported enum')
        if isinstance(value, dict):
            for key in node.get('required', []):
                if key not in value:
                    fail(f'{path}.{key}', 'required key is missing')
            for key, item in value.items():
                matched = False
                if key in node.get('properties', {}):
                    visit(item, node['properties'][key], f'{path}.{key}')
                    matched = True
                for pattern, child in node.get('patternProperties', {}).items():
                    if re.search(pattern, key):
                        visit(item, child, f'{path}.{key}')
                        matched = True
                if not matched:
                    extra = node.get('additionalProperties', True)
                    if extra is False:
                        fail(path, 'unknown property')
                    if isinstance(extra, dict):
                        visit(item, extra, f'{path}.{key}')
        if isinstance(value, list):
            if len(value) < node.get('minItems', 0) or len(value) > node.get('maxItems', MAX_NODES):
                fail(path, 'array length outside bounds')
            if node.get('uniqueItems') and any(equal(v, prior) for i, v in enumerate(value) for prior in value[:i]):
                fail(path, 'array entries must be unique')
            for i, item in enumerate(value):
                if 'items' in node:
                    visit(item, node['items'], f'{path}[{i}]')
        if isinstance(value, str):
            if len(value) < node.get('minLength', 0) or len(value) > node.get('maxLength', 16384):
                fail(path, 'string length outside bounds')
            if 'pattern' in node and not re.search(node['pattern'], value):
                fail(path, 'string does not match required pattern')
        if type(value) in (int, float) and (value < node.get('minimum', -math.inf) or value > node.get('maximum', math.inf)):
            fail(path, 'number outside bounds')
    bounded(data)
    visit(data, schema, '$')


def inspect_strings(value, path='$'):
    if isinstance(value, dict):
        for key, item in value.items():
            inspect_strings(key, '$key')
            if re.search(r'(?i)^(password|secret|api_key|access_token|private_key)$', key):
                fail(path, 'raw credential fields are forbidden; use environment references')
            inspect_strings(item, f'{path}.{key}')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            inspect_strings(item, f'{path}[{i}]')
    elif isinstance(value, str):
        if re.search(r'(?:sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|-----BEGIN .*PRIVATE KEY)', value):
            fail('$', 'secret-shaped credential rejected (known token pattern)')
        for token in re.findall(r'[A-Za-z0-9_+/=-]{32,}', value):
            if re.fullmatch(r'[a-fA-F0-9]{32,128}', token) or re.fullmatch(r'[A-Z0-9_]+', token):
                continue
            entropy = -sum((n / len(token)) * math.log2(n / len(token)) for n in collections.Counter(token).values())
            if entropy > 4.5 and re.search('[a-z]', token) and re.search('[A-Z]', token) and re.search('[0-9]', token):
                fail('$', 'secret-shaped high-entropy token rejected')
        if BYPASS.search(value):
            fail(path, 'permission-bypass flag is forbidden')


CANONICAL_IDENTITIES = frozenset((
    'software-factory', 'sf-agents', 'sf-crawl', 'sf-design', 'sf-eval', 'sf-evolve',
    'sf-help', 'sf-patterns', 'sf-principles', 'sf-refactor', 'sf-smell-audit',
    'sf-ai-engineer', 'sf-architect', 'sf-code-reviewer', 'sf-design-reviewer',
    'sf-engineer', 'sf-evaluator', 'sf-principal-engineer', 'sf-product-manager',
    'sf-qa-engineer', 'sf-release-engineer', 'sf-security-reviewer',
))


def governing_paths(data):
    """Configured authority is protected even when outside conventional locations."""
    docs = data['documents']
    paths = [*docs['principles'].values(), docs['architecture'], docs['conventions'],
             *docs.get('extra_context', []), data['tracker']['path'],
             *data.get('context', {}).values(), '.software-factory/context',
             'AGENTS.md', 'CLAUDE.md', 'PRINCIPLES.md', 'CONVENTIONS.md', 'ARCHITECTURE.md']
    decisions = [d['source'] for d in data['autonomy']['standing_delegations']]
    decisions += [e['write_authority']['source'] for e in data.get('environments', {}).values()
                  if 'write_authority' in e]
    paths += [source['data_policy_ref'] for source in data.get('operations', {}).get('sources', [])]
    paths += [bot['config'] for bot in data.get('review_bots', {}).values()]
    for entry in data.get('extensions', {}).get('mcp', []):
        paths.append(entry['config'])
        if 'consent' in entry:
            decisions.append(entry['consent']['path'])
    if data.get('operations', {}).get('authority_ref'):
        decisions.append(data['operations']['authority_ref'])
    for path in decisions:
        paths.append(path)
        parent = Path(path).parent.as_posix()
        if parent != '.':
            paths.append(parent)
    return paths


def aliases_path(value, paths):
    # Conservatively refuse case aliases on every host, including APFS/NTFS.
    parts = tuple(part.casefold() for part in Path(value).parts)
    return any(parts[:min(len(parts), len(p))] == p[:min(len(parts), len(p))]
               for p in (tuple(part.casefold() for part in Path(path).parts) for path in paths))


def validate_data(data, root, schema=None, *, check_paths=True):
    """Validate captured data; never reopen the source configuration.

    check_paths=False validates declarations only, not document availability.
    root may be a captured Path-like view for required document reads.
    """
    bounded(data)
    inspect_strings(data)
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        fail('$.version', 'unknown config version; expected integer version 1')
    schema = load(schema_path()) if schema is None else schema
    validate_schema(data, schema)
    def path_check(value, label, required=False):
        p = Path(value)
        if p.is_absolute() or '..' in p.parts or '\\' in value:
            fail(label, 'path must be relative and contained under project root')
        if check_paths:
            try:
                if isinstance(root, Path):
                    content = read_bytes(root, value) if required else None
                else:
                    content = (root / value).read_bytes() if required else None
                if required and (content is None or not content.strip()):
                    fail(label, 'referenced document must be nonempty')
                if not required and isinstance(root, Path):
                    current = root
                    for index, part in enumerate(p.parts):
                        current /= part
                        if current.is_symlink():
                            fail(label, 'symlink path is unsupported')
                        if current.exists() and index < len(p.parts) - 1 and not current.is_dir():
                            fail(label, 'existing path ancestor must be a directory')
                        if current.exists() and not (current.is_file() or current.is_dir()):
                            fail(label, 'special file path is unsupported')
            except (ConfigError, OSError, ValueError):
                fail(label, 'referenced path missing, empty, unreadable or unsafe')
    documents = data['documents']
    for key, value in documents['principles'].items():
        path_check(value, f'$.documents.principles.{key}', True)
    for key in ('architecture', 'conventions'):
        path_check(documents[key], f'$.documents.{key}', True)
    for value in documents.get('extra_context', []):
        path_check(value, '$.documents.extra_context', True)
    path_check(data['tracker']['path'], '$.tracker.path', True)
    for decision in data['autonomy']['standing_delegations']:
        path_check(decision['source'], '$.autonomy.standing_delegations.source', True)
    for key, value in data.get('context', {}).items():
        path_check(value, '$.context.' + key, True)
    for repo in data['project']['repositories'].values():
        path_check(repo['path'], '$.project.repositories.path')
    board = Path(data.get('board', {}).get('dir', '.software-factory/context/board')).as_posix()
    path_check(board, '$.board.dir')
    for key, value in data.get('bmad', {}).items():
        if key == 'custom_root':
            path_check(value, '$.bmad.custom_root')
    if data['branches']['integration'] in data['branches']['protected']:
        fail('$.branches.integration', 'integration branch is protected')
    agents, routing = data['agents'], data['routing']
    fallback = routing['fallback']
    if fallback not in agents or agents[fallback]['kind'] != 'native':
        fail('$.routing.fallback', 'fallback must name an existing native agent')
    for name in (routing['coding'], routing['independent_review'], *routing.get('complexity', {}).values()):
        if name not in agents:
            fail('$.routing', 'unknown agent reference')
    if set(agents[fallback]['risk_tiers']) != {0, 1, 2, 3}:
        fail('$.routing.fallback', 'native fallback must support every risk tier')
    def recipe(value, label):
        argv = value['argv']
        for token in argv:
            if not token.strip():
                fail(label, 'argv tokens must be nonempty')
            if ('{' in token or '}' in token) and token not in PLACEHOLDERS:
                fail(label, 'unknown or embedded placeholder; use documented whole tokens')
            if any(marker in token for marker in ('$(', '`', '\n', '\r')):
                fail(label, 'shell substitution is unsupported in argv')
        force = any(token == '--force' or token.startswith('--force=') for token in argv)
        if force and not (Path(argv[0]).name == 'cursor-agent' and '--workspace' in argv and argv.index('--workspace') + 1 < len(argv) and argv[argv.index('--workspace') + 1] == '{workspace}'):
            fail(label, '--force requires a pinned --workspace {workspace}')
        path_check(value['cwd'], label + '.cwd')
    for agent in agents.values():
        if agent['kind'] == 'external':
            recipe(agent['invoke'], '$.agents.invoke')
        detection = agent.get('detection', {})
        if 'path' in detection:
            path_check(detection['path'], '$.agents.detection.path')
    for env in data.get('environments', {}).values():
        if 'write_authority' in env:
            path_check(env['write_authority']['source'], '$.environments.write_authority.source', True)
        for key in ('deploy', 'proof'):
            if key in env:
                recipe(env[key], '$.environments.' + key)
    target = data['verification'].get('deploy_environment')
    if target and target not in data.get('environments', {}):
        fail('$.verification.deploy_environment', 'unknown environment reference')
    for bot in data.get('review_bots', {}).values():
        if bot['required'] and not bot['enabled']:
            fail('$.review_bots', 'required bot cannot be disabled')
        path_check(bot['config'], '$.review_bots.config')
    for group, entries in data.get('extensions', {}).items():
        identities, targets = set(), set()
        for entry in entries:
            identity = entry['id'].casefold().strip()
            if identity in identities or identity in CANONICAL_IDENTITIES:
                fail('$.extensions.' + group, 'duplicate or reserved identity')
            identities.add(identity)
            for key in ('source', 'target', 'config'):
                if key in entry:
                    path_check(entry[key], '$.extensions.' + group + '.' + key)
                    stores = (board, '.software-factory/runs', '.software-factory/config.yaml', '.software-factory/active.json', '.software-factory/installation.json', '.software-factory/runtime', '.software-factory/backups')
                    if aliases_path(entry[key], stores):
                        fail('$.extensions', 'extension aliases an authority store')
            if 'target' in entry:
                normalized = Path(entry['target']).as_posix()
                if normalized.casefold() in targets:
                    fail('$.extensions.overlays', 'duplicate overlay target')
                targets.add(normalized.casefold())
                if aliases_path(normalized, governing_paths(data)):
                    fail('$.extensions.overlays', 'target aliases configured governing documents or decisions')
            bindings = []
            if 'sha256' in entry and group == 'skills':
                bindings.append({'path': entry['source'], 'sha256': entry['sha256']})
            if 'manifest_sha256' in entry:
                bindings.append({'path': entry['source'], 'sha256': entry['manifest_sha256']})
            bindings += [entry[key] for key in ('provenance', 'consent') if key in entry]
            for binding in bindings:
                path_check(binding['path'], '$.extensions.' + group + '.binding', True)
                if check_paths:
                    raw = (read_bytes(root, binding['path']) if isinstance(root, Path)
                           else (root / binding['path']).read_bytes())
                    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
                        fail('$.extensions.' + group, 'declared source digest mismatch')
            if 'recipe' in entry:
                recipe(entry['recipe'], '$.extensions.recipe')
    operations = data.get('operations', {})
    if operations.get('enabled'):
        if not operations.get('sources') or not operations.get('authority_ref') or not operations.get('until'):
            fail('$.operations', 'enabled observation requires sources, authority_ref and until')
        path_check(operations['authority_ref'], '$.operations.authority_ref', True)
        for source in operations['sources']:
            if source['environment'] not in data.get('environments', {}):
                fail('$.operations.sources', 'unknown environment')
            path_check(source['data_policy_ref'], '$.operations.sources.data_policy_ref', True)
    plan = data.get('eval')
    if plan:
        surfaces = [s['id'] for s in plan['surfaces']]
        ids = [c['id'] for c in plan['cases']]
        if len(set(surfaces)) != len(surfaces) or len(set(ids)) != len(ids):
            fail('$.eval', 'surface and case IDs must be unique')
        if any(c['surface'] not in surfaces for c in plan['cases']):
            fail('$.eval.cases', 'unknown surface reference')
        path_check(plan['plan_file'], '$.eval.plan_file')
        path_check(plan['receipts_dir'], '$.eval.receipts_dir')
    return data


def validate_file(path, root=None):
    path = Path(path).absolute()
    data = load(path)
    if type(data.get('version')) is not int or data['version'] != 1:
        fail('$.version', 'unknown config version; expected integer version 1')
    declared = data.get('project', {}).get('root') if isinstance(data.get('project'), dict) else None
    if not isinstance(declared, str):
        fail('$.project.root', 'declared root is required')
    if Path(declared).is_absolute():
        fail('$.project.root', 'root must be relative to config directory')
    resolved = (path.parent / declared).resolve()
    if root is not None and resolved != Path(root).resolve():
        fail('$.project.root', 'declared root conflicts with explicit root')
    validate_data(data, resolved)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=['validate'], default='validate')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        validate_file(args.config, args.root)
    except (ConfigError, OSError, RecursionError, UnicodeError) as exc:
        print(f'config: {exc if isinstance(exc, ConfigError) else "unreadable or over-budget input"}', file=sys.stderr)
        return 1
    print('Configuration validated: syntax, schema and semantic references pass; no commands executed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
