"""Static artifact format/path/policy checks; never invokes host CLIs."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

import distribution


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_file(path):
    value = json.loads(path.read_text())
    require(isinstance(value, dict), 'expected JSON object')
    return value


def local(root, value):
    require(isinstance(value, str) and value.startswith('./'), 'path must start ./')
    require('..' not in Path(value).parts and '\\' not in value, 'unsafe component path')
    path = root / value
    require(path.exists() and path.resolve().is_relative_to(root.resolve()), 'missing/escaping path')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink component')
    return path


def schema_check(value, schema):
    """The small JSON Schema subset used by the vendored portable schema."""
    kinds = {'object': dict, 'array': list, 'string': str}
    if 'type' in schema:
        require(isinstance(value, kinds[schema['type']]), 'schema type mismatch')
    if 'const' in schema:
        require(value == schema['const'], 'schema constant mismatch')
    if isinstance(value, dict):
        require(set(schema.get('required', [])) <= value.keys(), 'missing schema field')
        fields = schema.get('properties', {})
        for key, item in value.items():
            extra = schema.get('additionalProperties', True)
            require(key in fields or extra is not False, 'unknown schema field')
            child = fields.get(key, extra if isinstance(extra, dict) else {})
            schema_check(item, child)
    if isinstance(value, list):
        for item in value:
            schema_check(item, schema.get('items', {}))
    if isinstance(value, str):
        require(len(value) >= schema.get('minLength', 0), 'schema minimum length')
        require(len(value) <= schema.get('maxLength', len(value)), 'schema maximum length')
        if 'pattern' in schema:
            require(re.search(schema['pattern'], value) is not None, 'schema pattern')


def portable(root, api):
    schema = json_file(api.PACK_ROOT / 'schemas/plugins/portable.schema.json')
    schema_check(json_file(root / 'plugin.json'), schema)
    require(len(list((root / 'skills').glob('*/SKILL.md'))) == 11, 'expected eleven skills')


def check(root, host, api):
    require(host in distribution.HOSTS, 'unknown host')
    catalog = json_file(root / distribution.CATALOGS[host])
    require(catalog.get('name') == 'software-factory-local', 'unexpected marketplace identity')
    require(isinstance(catalog.get('plugins'), list) and len(catalog['plugins']) == 1, 'expected one plugin')
    entry = catalog['plugins'][0]
    require(entry.get('name') == 'software-factory', 'unexpected plugin identity')
    if host == 'codex':
        require(entry.get('policy') == {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}, 'bad install policy')
        require(entry.get('category') == 'Productivity', 'bad category')
        require(isinstance(entry.get('source'), dict) and entry['source'].get('source') == 'local', 'bad source')
        plugin = local(root, entry['source']['path'])
        portable(plugin, api)
    else:
        require(catalog.get('owner') == {'name': 'Software Factory contributors'}, 'missing owner')
        plugin = local(root, entry['source'])
        manifest = '.claude-plugin/plugin.json' if host == 'claude-code' else '.cursor-plugin/plugin.json'
        data = json_file(plugin / manifest)
        require(data.get('name') == 'software-factory', 'unexpected native identity')
        require(data.get('skills') == ['./skills/'], 'bad skills paths')
        require('hooks' not in data, 'duplicate default hooks declaration')
        require(isinstance(data.get('agents'), list) and len(data['agents']) == 11, 'expected eleven roles')
        for kind in ('skills', 'agents', 'rules'):
            for value in data.get(kind, []):
                path = local(plugin, value)
                require(kind != 'agents' or path.is_file(), 'agent path must name a file')
    # Exact canonical projection comparison makes policy and hook drift a failure.
    expected = distribution.bundle_files(api, host)
    actual = {}
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'artifact symlink')
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = path.read_bytes()
    require(actual == expected, 'artifact differs from canonical host projection')
    require(len(list((plugin / 'skills').glob('*/SKILL.md'))) == 11, 'expected eleven skills')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--host', choices=distribution.HOSTS)
    args = parser.parse_args()
    api = distribution.load_api()
    try:
        portable(api.PACK_ROOT, api)
        if args.root:
            require(args.host is not None, '--root requires --host')
            check(args.root, args.host, api)
        else:
            with tempfile.TemporaryDirectory(prefix='sf-distribution-check-') as temporary:
                for host in distribution.HOSTS:
                    root = distribution.project(api, host, Path(temporary).resolve() / host)
                    check(root, host, api)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'distribution: {exc}\n')
    print('distribution: portable schema and three native profiles valid (static only)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
