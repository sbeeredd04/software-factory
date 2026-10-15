"""Read-only extension inspection and deterministic reviewed overlay composition.

Only install.py publishes composed Actions. Metadata and local artifact hashes are
provenance, never authenticated approval, service access or host execution proof.
"""
from __future__ import annotations

import argparse
import dataclasses
import difflib
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

SOURCE_LAYOUT = True  # Canonical projector sets False in every installed payload.
SUBJECT_FIELDS = ('version', 'id', 'target', 'base_sha256', 'mode', 'payload', 'evidence', 'author', 'risk')
MAX_OVERLAYS = 32


def module(path, name):
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded
    finally:
        sys.dont_write_bytecode = previous


agents = module(Path(__file__).absolute().parents[2] / 'sf-agents/scripts/agents.py', 'sf_evolve_agents')
config, discovery = agents.config, agents.discovery
Error, digest, encoded = agents.Error, agents.digest, agents.encoded


def artifact(data):
    """Every emitted artifact must round-trip through the bounded artifact reader."""
    raw = encoded(data)
    agents.parse_artifact(raw)
    return raw


def overlay_schema():
    here = Path(__file__).absolute()
    path = (here.parents[3] / 'schemas/overlay.schema.json' if SOURCE_LAYOUT
            else here.parent.parent / 'schemas/overlay.schema.json')
    return agents.read_json(path)


def subject(manifest):
    return digest(artifact({key: manifest[key] for key in SUBJECT_FIELDS}))


def bound_read(reader, binding):
    raw = reader.read(binding['path'])
    if raw is None or digest(raw) != binding['sha256']:
        raise Error('missing or changed bound evidence/payload')
    return raw


class CapturedRoot:
    """Config owns semantic validation; every required document read is captured."""
    def __init__(self, reader, relative=None):
        self.reader, self.relative = reader, relative

    def __truediv__(self, relative):
        return CapturedRoot(self.reader, relative)

    def read_bytes(self):
        raw = self.reader.read(self.relative)
        if raw is None:
            raise Error('required configuration reference is missing')
        return raw


def read_config(reader):
    raw = reader.read(discovery.CONFIG)
    if raw is None:
        return None
    data = config.parse(raw.decode('utf-8'))
    # Validate paths against the real root, then capture document reads and pins.
    config.validate_data(data, reader.root)
    config.validate_data(data, CapturedRoot(reader))
    declared = data['project']['root']
    if Path(declared).is_absolute() or (reader.root / '.software-factory' / declared).resolve() != reader.root:
        raise Error('configuration root does not match project')
    return data


def registry(root):
    reader = discovery.Reader(root)
    data = read_config(reader)
    results = {'skills': [], 'mcp': [], 'overlays': []}
    required = {'skills': ('upstream','revision','sha256','license','provenance','capabilities','triggers','phases','permissions'),
                'mcp': ('transport','capabilities','consent','provenance','auth_env'),
                'overlays': ('manifest_sha256',)}
    def unknown(value):
        return (value is None or (isinstance(value, str) and value.strip().casefold() in ('', 'unknown', 'noassertion', 'none'))
                or (isinstance(value, list) and any(unknown(item) for item in value)))
    for kind, entries in (data or {}).get('extensions', {}).items():
        for entry in entries:
            missing = [key for key in required[kind] if key not in entry
                       or unknown(entry[key])
                       or (key in ('capabilities','triggers','phases') and not entry[key])]
            # Metadata inspection never emits full skill instructions or reads MCP config.
            results[kind].append({'id': entry['id'], 'status': 'incomplete' if missing else 'declared',
                                  'missing': missing, 'adopted': False, 'connected': False})
    reader.finish()
    return {'schema': 'sf-extension-registry/1', 'entries': results, 'sources': reader.sources,
            'authority': 'host reconciliation required', 'configured': data is not None}


def safe_target(target, data=None):
    discovery.safe_path(target)
    parts = Path(target).parts
    if (len(parts) < 4 or parts[:2] not in (('.agents','skills'),('.claude','skills'))
            or parts[2] not in config.CANONICAL_IDENTITIES or parts[2] == 'software-factory'
            or not (parts[3:] == ('SKILL.md',) or
                    (len(parts) == 5 and parts[3] == 'references' and parts[4].endswith('.md')))):
        raise Error('overlay target must be a supported generated skill entry or Markdown reference')
    if data is not None and config.aliases_path(target, config.governing_paths(data)):
        raise Error('overlay target aliases configured governing documents or decisions')


def load_overlay(root, manifest_ref, *, reader=None, data=None):
    reader = reader or discovery.Reader(root)
    raw = reader.read(manifest_ref)
    if raw is None:
        raise Error('overlay manifest is missing')
    manifest = agents.parse_artifact(raw)
    config.validate_schema(manifest, overlay_schema())
    config.inspect_strings(manifest)
    expected = f".software-factory/overlays/{manifest['id']}/manifest.json"
    if manifest_ref != expected:
        raise Error('overlay manifest must use its canonical id directory')
    safe_target(manifest['target'], data)
    if manifest['subject_sha256'] != subject(manifest):
        raise Error('overlay proposal subject digest mismatch')
    for key in ('review', 'regression', 'canary', 'approval'):
        if manifest[key]['subject_sha256'] != manifest['subject_sha256']:
            raise Error('review, proof or approval is for a different proposal')
    if manifest['author'].casefold().strip() == manifest['review']['by'].casefold().strip():
        raise Error('independent non-author review is required')
    if manifest['risk'] == 'material' and manifest['approval']['kind'] != 'human':
        raise Error('material changes require a named human source decision')
    for key in ('author',):
        if manifest[key].strip().casefold() in ('unknown','none',''):
            raise Error('proposal author must be known')
    for key in ('review','approval'):
        if manifest[key]['by'].strip().casefold() in ('unknown','none',''):
            raise Error('review and approval provenance must be known')
    for key, fields in (('review', ('subject_sha256','verdict','by')),
                        ('regression', ('subject_sha256','result')),
                        ('canary', ('subject_sha256','result'))):
        receipt = agents.parse_artifact(bound_read(reader, manifest[key]['artifact']))
        if any(receipt.get(field) != manifest[key][field] for field in fields):
            raise Error('review or test receipt does not bind the declared subject and result')
    payload_path = manifest['payload']['path']
    discovery.safe_path(payload_path)
    if not payload_path.startswith(f".software-factory/overlays/{manifest['id']}/") or payload_path == manifest_ref:
        raise Error('payload must be separate and contained in its overlay directory')
    payload = bound_read(reader, manifest['payload'])
    for binding in [*manifest['evidence'], manifest['review']['artifact'],
                    manifest['regression']['artifact'], manifest['canary']['artifact'],
                    manifest['approval']['decision']]:
        raw_evidence = bound_read(reader, binding)
        if not raw_evidence.strip():
            raise Error('bound evidence must be nonempty')
        if binding['path'] in (manifest_ref, payload_path, manifest['target']):
            raise Error('evidence must be separate from proposal, payload and target')
    reader.finish()
    return manifest, payload


def frontmatter(raw):
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != b'---':
        raise Error('generated skill entry lacks frontmatter')
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == b'---':
            return b''.join(lines[:index+1])
    raise Error('generated skill frontmatter is unterminated')


def plan_overlay(base_bytes, manifest, payload_bytes):
    """Exact bytes only: no filesystem writes, fuzz, implicit newline or force."""
    if digest(base_bytes) != manifest['base_sha256']:
        raise Error('upstream base changed; propose a new reviewed rebase; no bytes applied')
    if digest(payload_bytes) != manifest['payload']['sha256']:
        raise Error('overlay payload digest mismatch')
    after = base_bytes + payload_bytes if manifest['mode'] == 'append' else payload_bytes
    if len(after) > config.MAX_BYTES:
        raise Error('composed overlay exceeds 1MiB budget')
    try:
        after.decode('utf-8')
    except UnicodeDecodeError:
        raise Error('overlay must produce UTF-8 Markdown') from None
    if Path(manifest['target']).name == 'SKILL.md' and frontmatter(after) != frontmatter(base_bytes):
        raise Error('overlay cannot change generated identity, invocation or permission frontmatter')
    return after


def overlay_actions(root, projected_actions):
    """Compose prior to planning; attach captured inputs to the existing transaction."""
    reader = discovery.Reader(root)
    data = read_config(reader)
    entries = (data or {}).get('extensions', {}).get('overlays', [])
    if len(entries) > MAX_OVERLAYS:
        raise Error('overlay count exceeds transaction budget')
    by_path = {action.path: action for action in projected_actions}
    overlaid = set()
    for entry in entries:
        if 'manifest_sha256' not in entry:
            raise Error('registered overlay is incomplete: manifest_sha256 required for composition')
        raw = bound_read(reader, {'path':entry['source'], 'sha256':entry['manifest_sha256']})
        del raw
        manifest, payload = load_overlay(root, entry['source'], reader=reader, data=data)
        if any(entry[key] != manifest[key] for key in ('id','target','base_sha256')):
            raise Error('overlay registry and manifest bindings disagree')
        action = by_path.get(entry['target'])
        if action is None or action.kind != 'write' or action.content is None:
            raise Error('overlay target is absent from selected host projection')
        if action.path in overlaid:
            raise Error('multiple overlays for one target are unsupported')
        by_path[action.path] = dataclasses.replace(action, content=plan_overlay(action.content, manifest, payload), overlay=True)
        overlaid.add(action.path)
    reader.finish()
    return [dataclasses.replace(by_path[a.path], inputs=dict(reader.sources), root_identity=tuple(reader.identity)) for a in projected_actions]


def revalidate(root, sources):
    reader = discovery.Reader(root)
    for path, expected in sources.items():
        raw = reader.read(path)
        if (None if raw is None else digest(raw)) != expected:
            raise Error('overlay/configuration input changed during installation')
    reader.finish()


def inspect_overlay(root, manifest_ref, base_ref):
    reader = discovery.Reader(root)
    data = read_config(reader)
    manifest, payload = load_overlay(root, manifest_ref, reader=reader, data=data)
    base = reader.read(base_ref)
    if base is None:
        raise Error('explicit generated base reference is missing')
    try:
        after = plan_overlay(base, manifest, payload)
        status, reason = 'proposed', 'bound artifacts checked; actual GO and review independence remain host-owned'
    except Error as exc:
        if digest(base) == manifest['base_sha256']:
            raise
        after = base + payload if manifest['mode'] == 'append' else payload
        status, reason = 'conflict', str(exc)
    diff = ''.join(difflib.unified_diff(base.decode('utf-8').splitlines(True),
                                     after.decode('utf-8').splitlines(True),
                                     fromfile='observed-base', tofile='reviewed-candidate'))
    reader.finish()
    result = {'schema':'sf-overlay-proposal/1', 'status':status, 'reason':reason,
              'subject_sha256':manifest['subject_sha256'], 'base_sha256':digest(base),
              'candidate_sha256':digest(after) if status == 'proposed' else None,
              'diff':diff, 'sources':reader.sources, 'applied':False}
    artifact(result)
    return result


def merge_customization(base, override):
    """Static structural preview, never proof of an upstream resolver invocation."""
    if isinstance(base, dict) and isinstance(override, dict):
        return {**base, **{key: merge_customization(base[key], value) if key in base else value
                          for key, value in override.items()}}
    if isinstance(base, list) and isinstance(override, list):
        combined = base + override
        for field in ('code', 'id'):
            if combined and all(isinstance(item, dict) and field in item for item in combined):
                if any(not isinstance(item[field], str) or not item[field] for item in combined):
                    raise Error('customization array IDs must be nonempty strings')
                result = list(base)
                positions = {item[field]: index for index, item in enumerate(result)}
                for item in override:
                    if item[field] in positions:
                        result[positions[item[field]]] = item
                    else:
                        positions[item[field]] = len(result)
                        result.append(item)
                return result
        return combined
    return override


def unsupported_fields(changes, base, prefix=''):
    missing = []
    for key, value in changes.items():
        name = prefix + key
        if key not in base:
            missing.append(name)
        elif isinstance(value, dict):
            if not isinstance(base[key], dict):
                missing.append(name)
            else:
                missing.extend(unsupported_fields(value, base[key], name + '.'))
        elif type(value) is not type(base[key]):
            missing.append(name)
    return missing


def bmad_inspect(root, base_ref, changes=None):
    """Observe exact installed layers; stop before dispatch on unknown callbacks."""
    reader = discovery.Reader(root)
    base_path = discovery.safe_path(base_ref)
    skill = base_path.parent.name
    if base_path.name != 'customize.toml' or not re.fullmatch(r'bmad-[a-z0-9-]+', skill):
        raise Error('base must name an installed BMad skill customize.toml')
    here = Path(__file__).absolute()
    parser_path = (here.parents[3] / 'scripts/bmad_install.py' if SOURCE_LAYOUT
                   else here.with_name('bmad_install.py'))
    parser = module(parser_path, 'sf_evolve_bmad_metadata')
    version_raw = reader.read('_bmad/_config/manifest.yaml')
    version = None if version_raw is None else parser.parse_manifest(version_raw)['version']
    layers, names = [], [base_ref, f'_bmad/custom/{skill}.toml', f'_bmad/custom/{skill}.user.toml']
    for name in names:
        raw = reader.read(name)
        if name == base_ref and raw is None:
            raise Error('installed customize.toml missing; supported fields are unknown')
        layer = {} if raw is None else tomllib.loads(raw.decode('utf-8'))
        config.bounded(layer)
        layers.append(layer)
    changes = changes or {}
    config.bounded(changes)
    config.inspect_strings(changes)
    missing = unsupported_fields(changes, layers[0])
    effective = merge_customization(merge_customization(layers[0], layers[1]), layers[2])
    proposed = merge_customization(merge_customization(layers[0], merge_customization(layers[1], changes)), layers[2])
    # Callback prose can encode arbitrary indirect routes. Nonempty callbacks
    # require host inspection even if no literal factory spelling is detected.
    callbacks = []
    def visit(value, prefix=''):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('on_complete','implementation_handoff','activation_steps_prepend','activation_steps_append') and item:
                    callbacks.append((prefix + key, item))
                visit(item, prefix + key + '.')
        elif isinstance(value, list):
            for item in value:
                visit(item, prefix)
    visit(effective)
    visit(proposed)
    recursive = any(re.search(r'(?i)(software[ _-]factory|sf-evolve|sf-agents)', json.dumps(value))
                    for _, value in callbacks)
    status = ('unsupported' if version != '6.12.0' or missing else
              'recursive' if recursive else 'needs-host-review')
    reader.finish()
    return {'schema':'sf-bmad-customization-proposal/1', 'status':status, 'observed_version':version,
            'unsupported_fields':missing, 'callback_fields':sorted({key for key, _ in callbacks}),
            'team_target':names[1], 'sources':reader.sources, 'applied':False,
            'resolver_executed':False, 'dispatch_allowed':False,
            'effective_sha256':digest(artifact(effective)), 'proposed_sha256':digest(artifact(proposed)),
            'changes_sha256':digest(artifact(changes)),
            'next':'record a finite delegation boundary and inspect effective callbacks before host dispatch; native fallback remains available'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('registry','inspect','propose','bmad-inspect'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--base', help='contained file holding exact generated upstream bytes')
    parser.add_argument('--changes', help='contained JSON object of proposed sparse BMad keys')
    args = parser.parse_args()
    try:
        if args.command == 'registry':
            result = registry(args.root)
        elif args.command == 'bmad-inspect':
            if not args.base:
                raise Error('bmad-inspect requires --base')
            changes = None if not args.changes else agents.parse_artifact(config.read_bytes(args.root, discovery.safe_path(args.changes)))
            result = bmad_inspect(args.root, args.base, changes)
        else:
            if not args.manifest or not args.base:
                raise Error('inspect/propose require --manifest and --base')
            result = inspect_overlay(args.root, args.manifest, args.base)
        sys.stdout.buffer.write(artifact(result))
        return 1 if result.get('status') == 'conflict' else 0
    except (Error, config.ConfigError) as exc:
        print('evolve: ' + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, RecursionError):
        print('evolve: unreadable, malformed or over-budget input; inspect source bindings and shipped schema', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
