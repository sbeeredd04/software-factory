#!/bin/sh
# Runs in the consumer workspace; the plugin bundle is read-only input.
set -u
if ! command -v python3 >/dev/null 2>&1 ||
   ! python3 -I -B -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
  printf '%s\n' 'Software Factory recovery warning: Python 3.11 or newer is required.'
  exit 0
fi
sf_plugin_scripts=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 0
python3 -I -B "$sf_plugin_scripts/dispatch.py" "$@" 2>&1 ||
  printf '%s\n' 'Software Factory recovery warning: helper unavailable; reconcile manually.'
exit 0
