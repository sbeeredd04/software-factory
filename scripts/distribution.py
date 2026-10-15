"""Deterministic native marketplace projections, without consumer installation."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

HOSTS = ('claude-code', 'cursor', 'codex')
CATALOGS = {'claude-code': '.claude-plugin/marketplace.json',
            'cursor': '.cursor-plugin/marketplace.json',
            'codex': '.agents/plugins/marketplace.json'}
PLUGIN = 'plugins/software-factory'


def load_api(root=None):
    # Dynamic imports must not leave bytecode in the source checkout.
    sys.dont_write_bytecode = True
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    path = root / 'install.py'
    spec = importlib.util.spec_from_file_location('sf_distribution_installer', path)
    api = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = api
    spec.loader.exec_module(api)
    return api


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def safe_sources(root):
    """Refuse symlinks before existing projectors can follow them."""
    for folder in ('skills', 'agents', 'hosts'):
        base = root / folder
        if base.is_symlink():
            raise ValueError('symlink source refused')
        for path in base.rglob('*'):
            if path.is_symlink():
                raise ValueError('symlink source refused')


def hook_config(api, host):
    variable = {'claude-code': 'CLAUDE_PLUGIN_ROOT', 'cursor': 'CURSOR_PLUGIN_ROOT',
                'codex': 'PLUGIN_ROOT'}[host]

    def command(event):
        return f'sh "${{{variable}}}/scripts/hook.sh" --host {host} --event {event}'

    if host == 'cursor':
        return {'version': 1, 'hooks': {
            event: [{'command': command(normalized)}]
            for event, normalized in api.CURSOR_HOOK_EVENTS}}
    return {'hooks': {event: [{'matcher': matcher, 'hooks': [
        {'type': 'command', 'command': command(normalized)}]}]
        for event, matcher, normalized in api.HOOK_EVENTS}}


def bundle_files(api, host):
    if host not in HOSTS:
        raise ValueError('choose claude-code, cursor, codex, or all')
    safe_sources(api.PACK_ROOT)
    files = {}
    policy = api.load_policy(host)
    actions = (api.project_claude(api.PACK_ROOT, policy, 'full') if host == 'claude-code'
               else api.project_shared_skills([host]) + api.PROJECTORS[host](api.PACK_ROOT, policy, 'full'))
    for action in actions:
        if action.kind != 'write':
            continue
        path = action.path
        for prefix in ('.claude/skills/', '.agents/skills/'):
            if path.startswith(prefix):
                files['skills/' + path[len(prefix):]] = action.content
        for prefix in ('.claude/agents/', '.cursor/agents/'):
            if path.startswith(prefix):
                files['agents/' + path[len(prefix):]] = action.content
        if path.startswith('.codex/agents/'):
            # Packaged for manual use, never claim undocumented plugin registration.
            files['role-prompts/' + Path(path).name] = action.content
        if path.startswith(api.RUNTIME_REL + '/'):
            files['scripts/' + Path(path).name] = action.content
    for name in ('hook.sh', 'dispatch.py'):
        files['scripts/' + name] = (api.PACK_ROOT / 'hosts/plugins' / name).read_bytes()
    for name in ('LICENSE', 'NOTICE.md'):
        files[name] = (api.PACK_ROOT / name).read_bytes()
    files['hooks/hooks.json'] = encoded(hook_config(api, host))
    metadata = json.loads((api.PACK_ROOT / 'plugin.json').read_text())
    metadata['version'] = api.PACK_VERSION
    metadata['description'] = 'Software Factory native skills and recovery hooks; project setup uses the installer.'
    if host == 'codex':
        files['plugin.json'] = encoded(metadata)
        files['role-prompts/README.md'] = (
            b'These eleven generated TOML roles are reference/manual setup material.\n'
            b'Automatic plugin registration is unverified. Use the project installer\n'
            b'for custom agents; permissions inherit the parent session.\n')
    else:
        metadata.pop('$schema')
        metadata['skills'] = ['./skills/']
        metadata['agents'] = ['./' + name for name in sorted(files) if name.startswith('agents/')]
        if host == 'cursor':
            metadata['rules'] = ['./rules/']
            files['rules/software-factory.mdc'] = (api.PACK_ROOT / 'hosts/plugins/cursor.mdc').read_bytes()
        manifest = '.claude-plugin/plugin.json' if host == 'claude-code' else '.cursor-plugin/plugin.json'
        files[manifest] = encoded(metadata)
    catalog = {'name': 'software-factory-local', 'plugins': [
        {'name': 'software-factory', 'source': './' + PLUGIN}]}
    if host == 'codex':
        catalog['plugins'][0].update(source={'source': 'local', 'path': './' + PLUGIN},
                                     policy={'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                                     category='Productivity')
    else:
        catalog['owner'] = {'name': 'Software Factory contributors'}
    return {**{PLUGIN + '/' + name: data for name, data in files.items()},
            CATALOGS[host]: encoded(catalog)}


def output_path(out, source):
    """Only create a new leaf under an existing, nonsymlink parent."""
    out = Path(out).absolute()
    if '..' in out.parts or any(p.is_symlink() for p in (out, *out.parents)):
        raise ValueError('unsafe output path')
    resolved = out.resolve()
    source = source.resolve()
    if (resolved == source or resolved in source.parents
            or (source in resolved.parents and not resolved.is_relative_to(source / 'dist'))):
        raise ValueError('output must be external or under ignored dist/')
    if out.exists() or not out.parent.is_dir():
        raise ValueError('output must not exist and its parent must exist')
    return out


def write_new(out, files, source):
    """Exclusive output ownership; cleanup incomplete trees on failure/interruption."""
    out = output_path(out, source)
    out.mkdir(mode=0o755)
    try:
        for rel, data in sorted(files.items()):
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755 if path.suffix == '.sh' else 0o644)
        for path in out.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
        out.chmod(0o755)
    except BaseException:
        shutil.rmtree(out)
        raise
    return out


def project(api, host, out):
    selected = HOSTS if host == 'all' else (host,)
    files = {}
    for selected_host in selected:
        prefix = selected_host + '/' if host == 'all' else ''
        files.update({prefix + rel: data for rel, data in bundle_files(api, selected_host).items()})
    return write_new(out, files, api.PACK_ROOT)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=(*HOSTS, 'all'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        project(load_api(), args.host, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'distribution: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
