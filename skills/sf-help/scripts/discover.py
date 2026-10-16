"""Bounded, read-only onboarding observations; sf-crawl owns repository crawling."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

MAX_FILES = 128
CONFIG = '.software-factory/config.yaml'
CRAWL = '.software-factory/context/CODEBASE.md'
RECEIPT = '.software-factory/setup-receipt.json'
DOCS = ('README.md', 'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING.md', 'PRINCIPLES.md', 'ARCHITECTURE.md', 'CONVENTIONS.md')
BOTS = {'greptile':('greptile.json','.greptile/config.json'), 'coderabbit':('.coderabbit.yaml',), 'bugbot':('.cursor/BUGBOT.md','.cursor/config/bugbot.yaml'), 'copilot':('.github/copilot-instructions.md',)}


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


config = module(Path(__file__).absolute().parents[2] / 'software-factory/scripts/config.py', 'sf_setup_config')


class SetupError(ValueError):
    pass


def digest(content):
    return hashlib.sha256(content).hexdigest()


def encoded(data):
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def safe_path(value):
    if not isinstance(value, str) or len(value) > 512:
        raise SetupError('invalid relative path')
    path = Path(value)
    if path.is_absolute() or not path.parts or '..' in path.parts or '\\' in value or path.as_posix() != value:
        raise SetupError('path must be canonical and contained')
    for part in path.parts:
        lower = part.lower()
        if lower.startswith('.env') or lower in {'auth.json','credentials','credentials.json','secrets','transcripts','node_modules','.git','.ssh','.aws','.venv','venv','__pycache__'} or lower.endswith(('.pem','.key','.p12','.pfx')):
            raise SetupError('excluded sensitive or generated path')
    return path


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise SetupError('project must be a directory')
        info = self.root.stat()
        self.identity = [info.st_dev,info.st_ino]
        self.sources = {}
        self.directories = {}
        self.directory_entries = {}

    def check_root(self):
        info = self.root.lstat()
        if [info.st_dev,info.st_ino] != self.identity:
            raise SetupError('project root changed during observation')

    def read(self, relative):
        self.check_root()
        safe_path(relative)
        if len(self.sources) >= MAX_FILES and relative not in self.sources:
            raise SetupError('observation file budget exceeded')
        try:
            raw = config.read_bytes(self.root, relative, required=False)
        except config.ConfigError as exc:
            raise SetupError(str(exc)) from None
        fingerprint = None if raw is None else digest(raw)
        if relative in self.sources and self.sources[relative] != fingerprint:
            raise SetupError('source changed during discovery')
        self.sources[relative] = fingerprint
        self.check_root()
        return raw

    def names(self, relative):
        path = Path('.') if relative == '.' else safe_path(relative)
        fds = []
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fds.append(fd)
            for part in path.parts:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                fds.append(fd)
            names = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    if len(names) >= MAX_FILES:
                        raise SetupError('directory entry budget exceeded')
                    names.append(entry.name)
            for index, part in enumerate(path.parts):
                observed, opened = os.stat(part, dir_fd=fds[index], follow_symlinks=False), os.fstat(fds[index+1])
                if (observed.st_dev,observed.st_ino) != (opened.st_dev,opened.st_ino):
                    raise SetupError('directory changed during observation')
            self.check_root()
            names.sort()
            entry_hashes = sorted(digest(name.encode()) for name in names)
            fingerprint = digest(encoded(entry_hashes))
            if relative in self.directories and self.directories[relative] != fingerprint:
                raise SetupError('directory changed during observation')
            self.directories[relative] = fingerprint
            self.directory_entries[relative] = entry_hashes
            return names
        except FileNotFoundError:
            if relative in self.directories and self.directories[relative] is not None:
                raise SetupError('directory disappeared during observation') from None
            self.directories[relative] = None
            self.directory_entries[relative] = None
            return []
        except OSError:
            raise SetupError('unsafe observation directory') from None
        finally:
            for fd in reversed(fds):
                os.close(fd)

    def finish(self):
        for relative, expected in list(self.sources.items()):
            self.read(relative)
            if self.sources[relative] != expected:
                raise SetupError('source changed during observation')
        for relative in list(self.directories):
            self.names(relative)


def clean(value):
    try:
        config.bounded(value)
        config.inspect_strings(value)
        return value
    except config.ConfigError:
        return None


def discover(root, *, path=None):
    reader = Reader(root)
    crawl = reader.read(CRAWL)
    result = {'schema':'sf-onboarding-discovery/1', 'crawl':{'path':CRAWL,'sha256':reader.sources[CRAWL], 'status':'observed' if crawl is not None else 'missing'},
              'root_identity':reader.identity,
              'languages':[], 'package_managers':[], 'commands':[], 'documents':[], 'bots':{},
              'ci':{'provider':None,'workflows':[], 'required_checks':'unknown'},
              'repo':{'head':'unknown','remotes':'unknown','protected_branches':'unknown','dirty_paths':'unknown','worktrees':'unknown'},
              'capabilities':{'auth':'unknown','effective_models':'unknown','monitoring':'unknown','scheduling':'unknown'}}
    raw = reader.read('pyproject.toml')
    if raw is not None:
        result['languages'].append('Python')
        result['package_managers'].append('pip')
        try:
            project = tomllib.loads(raw.decode())
            if isinstance(project.get('tool'),dict) and 'pytest' in project['tool']:
                result['commands'].append({'argv':['python3','-m','pytest'], 'status':'inferred','source':'pyproject.toml'})
        except (ValueError, UnicodeError):
            result['python_manifest'] = 'unparseable'
    if reader.read('requirements.txt') is not None and 'Python' not in result['languages']:
        result['languages'].append('Python')
        result['package_managers'].append('pip')
    raw = reader.read('package.json')
    if raw is not None:
        try:
            package = config.parse(raw.decode())
        except (config.ConfigError, UnicodeError):
            package = {}
        dependencies = package.get('devDependencies')
        typescript = reader.read('tsconfig.json') is not None or (isinstance(dependencies,dict) and 'typescript' in dependencies)
        result['languages'].append('TypeScript' if typescript else 'JavaScript')
        manager = str(package.get('packageManager','npm')).split('@')[0]
        manager = manager if manager in ('npm','pnpm','yarn','bun') else 'unknown'
        result['package_managers'].append(manager)
        scripts = package.get('scripts', {})
        for key in ('test','build','lint','format','dev'):
            if isinstance(scripts,dict) and isinstance(scripts.get(key),str):
                result['commands'].append({'argv':[manager,'run',key], 'declaration':clean(scripts[key]), 'status':'observed-declaration-unexecuted','source':'package.json'})
    for filename, language, manager in (('go.mod','Go','go'),('Cargo.toml','Rust','cargo')):
        if reader.read(filename) is not None:
            result['languages'].append(language)
            result['package_managers'].append(manager)
    for filename in DOCS:
        if reader.read(filename) is not None:
            result['documents'].append(filename)
    for bot, paths in BOTS.items():
        result['bots'][bot] = {'configs':[p for p in paths if reader.read(p) is not None], 'active':'unknown'}
    for name in reader.names('.github/workflows'):
        if re.fullmatch(r'[A-Za-z0-9_.-]+\.ya?ml',name) and reader.read('.github/workflows/'+name) is not None:
            result['ci']['workflows'].append('.github/workflows/'+name)
    if result['ci']['workflows']:
        result['ci']['provider'] = 'github-actions'
    bmad_paths = ('_bmad/_config/manifest.yaml','_bmad/config.toml','skills-lock.json')
    present = [p for p in bmad_paths if reader.read(p) is not None]
    reader.names('_bmad')
    tree_present = reader.directories['_bmad'] is not None
    result['bmad'] = {'paths':present, 'tree_present':tree_present, 'version':'unknown', 'modules':'unknown', 'host_coverage':'unknown', 'planning_model':'unknown', 'action':'preserve-and-observe' if present or tree_present else 'optional'}
    manifest = reader.read(bmad_paths[0])
    if manifest:
        version = re.search(rb'(?m)^  version: [\'"]?([0-9]+\.[0-9]+\.[0-9]+)[\'"]?\s*$',manifest)
        if version:
            result['bmad']['version'] = version[1].decode()
    result['binaries'] = {name:shutil.which(name,path=path) is not None for name in ('claude','cursor-agent','codex','gh','node','npm','npx','uv')}
    root_names = reader.names('.')
    result['root_entries_sha256'] = digest(encoded(root_names))
    result['greenfield'] = not set(root_names) - {'.git','.keep'}
    result['layout'] = 'greenfield-candidate' if result['greenfield'] else 'existing' if crawl is not None or result['languages'] else 'unrecognized; structure unknown'
    result['test_command'] = next((c for c in result['commands'] if 'test' in c['argv'] or 'pytest' in c['argv']),None)
    result['config_present'] = reader.read(CONFIG) is not None
    reader.finish()
    result['sources'] = reader.sources
    result['directories'] = reader.directories
    result['directory_entries'] = reader.directory_entries
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--json',action='store_true',help='JSON is always emitted')
    args = parser.parse_args()
    try:
        print(encoded(discover(args.project)).decode(),end='')
    except (SetupError, OSError, ValueError) as exc:
        parser.exit(1, f'discover: {exc if isinstance(exc,SetupError) else "unsafe or invalid input"}\n')


if __name__ == '__main__':
    main()
