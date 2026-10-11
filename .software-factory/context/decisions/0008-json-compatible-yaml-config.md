# 0008 — JSON-compatible YAML configuration in v1

Status: accepted · 2026-10-11

## Context

The consumer config is `.software-factory/config.yaml`. Helpers must parse
it with the standard library only.

## Drivers

- The brief selects YAML; helpers stay dependency-free.
- JSON is valid YAML and parses predictably with `json.loads`.

## Options

- Full YAML via a third-party parser: ergonomic but a shipped dependency.
- A custom partial YAML parser: ambiguous and misleading.
- Emit and accept the JSON-compatible subset, with a strict JSON Schema
  2020-12 plus semantic validation.

## Outcome

Config is JSON-compatible YAML parsed with stdlib `json`, because
predictable parsing without dependencies beats partial YAML support.

## Consequences

- Deliberately less ergonomic than conventional YAML; the doctor explains
  unsupported YAML instead of guessing.
- An optional full-YAML import may arrive later as an explicit converter,
  never a hidden fallback.

## Confirmation

- `tests/test_config_kernel.py` covers the subset parser and semantic
  checks; schema validation lands with the config milestone.
