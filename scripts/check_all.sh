#!/usr/bin/env bash
# check_all.sh - the single static gate for the Software Factory pack.
#
# Runs every local check in a fixed order and exits nonzero if any step
# fails, naming the failed step. Set SF_SKIP_NETWORK=1 to skip the
# network-dependent steps (Mermaid rendering, the uvx-based Agent Skills
# and JSON Schema validators) so offline runs and separate CI jobs stay
# possible; those steps then report as skipped, never as passed.
#
# The commands here mirror CONTRIBUTING.md ("The verification gate") and
# .github/workflows/ci.yml; keep all three in sync.

set -u
cd "$(dirname "$0")/.." || exit 1

FAILED_STEPS=()
SKIPPED_STEPS=()

run_step() {
  local name="$1"
  shift
  printf '\n==> %s\n' "$name"
  if "$@"; then
    printf 'ok: %s\n' "$name"
  else
    local rc=$?
    printf 'FAILED: %s (exit %s)\n' "$name" "$rc"
    FAILED_STEPS+=("$name")
  fi
}

skip_step() {
  printf '\n==> %s: skipped (SF_SKIP_NETWORK=1, unverified - not a pass)\n' "$1"
  SKIPPED_STEPS+=("$1")
}

run_step "compileall" python3 -m compileall -q install.py scripts skills tests
run_step "unit tests" python3 -m unittest discover -s tests -v
run_step "ruff" uvx ruff check .

if [ -f install.sh ]; then
  run_step "shellcheck" npx -y shellcheck@latest install.sh
else
  printf '\n==> shellcheck: skipped (no install.sh yet)\n'
fi

run_step "validate" python3 scripts/validate.py
run_step "scan_public" python3 scripts/scan_public.py
run_step "check_links" python3 scripts/check_links.py

if [ "${SF_SKIP_NETWORK:-0}" = "1" ]; then
  skip_step "check_mermaid"
  skip_step "agentskills validate"
  skip_step "check-jsonschema"
else
  run_step "check_mermaid" python3 scripts/check_mermaid.py

  for skill in skills/*/; do
    [ -d "$skill" ] || continue
    run_step "agentskills validate ${skill%/}" \
      uvx --from skills-ref agentskills validate "${skill%/}"
  done

  shopt -s nullglob
  workflows=(.github/workflows/*.yml)
  issue_forms=(.github/ISSUE_TEMPLATE/*.yml)
  shopt -u nullglob
  if [ "${#workflows[@]}" -gt 0 ]; then
    run_step "check-jsonschema workflows" \
      uvx check-jsonschema --builtin-schema vendor.github-workflows "${workflows[@]}"
  fi
  if [ "${#issue_forms[@]}" -gt 0 ]; then
    run_step "check-jsonschema issue forms" \
      uvx check-jsonschema --builtin-schema vendor.github-issue-forms "${issue_forms[@]}"
  fi
fi

printf '\n'
if [ "${#FAILED_STEPS[@]}" -gt 0 ]; then
  printf 'check_all: FAILED steps: %s\n' "${FAILED_STEPS[*]}"
  exit 1
fi
if [ "${#SKIPPED_STEPS[@]}" -gt 0 ]; then
  printf 'check_all: all run steps passed; skipped (unverified): %s\n' "${SKIPPED_STEPS[*]}"
else
  printf 'check_all: all steps passed\n'
fi
exit 0
