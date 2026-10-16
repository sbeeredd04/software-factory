"""Select the consumer workspace from host input before running recovery."""
import importlib.util
import io
import json
import sys
from pathlib import Path


def main():
    try:
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError('oversized input')
        payload = json.loads(raw or '{}')
        if not isinstance(payload, dict):
            raise TypeError('invalid input')
        host = sys.argv[sys.argv.index('--host') + 1]
        if host == 'cursor':
            roots = payload.get('workspace_roots', [])
            if not isinstance(roots, list) or len(roots) != 1:
                raise ValueError('ambiguous consumer workspace')
            workspace = roots[0]
        else:
            workspace = payload.get('cwd')
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise ValueError('missing consumer workspace')
        if not Path(workspace).is_dir():
            raise ValueError('unavailable consumer workspace')
        spec = importlib.util.spec_from_file_location('sf_plugin_hook', Path(__file__).with_name('hook.py'))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        sys.stdin = io.StringIO(raw)
        sys.argv.extend(['--workspace', workspace])
        return hook.main()
    except Exception:  # noqa: BLE001 - recovery never blocks the host
        print('Software Factory recovery warning: consumer workspace could not be read; reconcile manually.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
