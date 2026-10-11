# Fixture: python-cli

A tiny Python CLI package used by the crawl tests. Expected findings:

- Modules: `fixture_cli`, `fixture_cli.cli`, `fixture_cli.core`,
  `fixture_cli.__main__`.
- Internal import edges: `fixture_cli.cli` imports `fixture_cli.core`;
  `fixture_cli.__main__` imports `fixture_cli.cli`.
- Entry points: the `fixture-cli` script in `pyproject.toml`, the
  `__main__` guard in `fixture_cli/cli.py`, and `fixture_cli/__main__.py`.
- Calls: `main` calls `Engine` (resolves to `fixture_cli.core.Engine`);
  `Engine.render` calls `format_payload` (same module).
