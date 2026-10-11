# 0009 — Preserve settings, back up changes, own exact writes

Status: accepted · 2026-10-11

## Context

Consumer settings may hold irreplaceable customization or secrets and may
not be tracked by Git. Installation cannot assume a clean checkout.

## Drivers

- Overwriting host directories destroys user work.
- Uninstall must remove only what the installer owns, unchanged.

## Options

- Overwrite and rely on Git rollback: unsafe when files are untracked.
- Broad recursive uninstall: removes user content.
- Before/after hashes, an ownership manifest, path-specific overwrite
  consent, backups before every overwrite, and structural merges.

## Outcome

The installer maintains an ownership manifest and backs up before every
overwrite; uninstall restores or removes only unchanged owned content,
because exact ownership is the only safe write policy on unknown trees.

## Consequences

- Backups get private permissions and ignore rules; never uploaded.
- Malformed settings and concurrent modification fail safe.
- A multi-file transaction needs a journal; atomic replace alone is not
  an atomic install.

## Confirmation

- Installer tests cover idempotency, backups, settings merges and
  uninstall safety (installer milestone).
