#!/bin/sh
set -eu

root=$(git rev-parse --show-toplevel)
hook=$(git -C "$root" rev-parse --git-path hooks/pre-push)
mkdir -p "$(dirname "$hook")"

cat > "$hook" <<'HOOK'
#!/bin/sh
set -eu

root=$(git rev-parse --show-toplevel)
cd "$root"

if command -v python >/dev/null 2>&1; then
  python_cmd=python
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=python3
else
  echo "RULE PRE_PUSH_PYTHON FAILED: Python is unavailable. REMEDY: install Python 3 and retry the push." >&2
  exit 1
fi

FOUNDER_NAME_PATTERNS=$($python_cmd scripts/derive_founder_patterns.py --validate)
export FOUNDER_NAME_PATTERNS
STATE_PRESERVE_TIMESTAMP=1
export STATE_PRESERVE_TIMESTAMP

$python_cmd scripts/generate_state.py
if ! git diff --exit-code -- docs/STATE.md; then
  echo "RULE STATE_FRESHNESS FAILED: docs/STATE.md differs from repository facts. REMEDY: run 'python scripts/generate_state.py' and commit docs/STATE.md." >&2
  exit 1
fi
$python_cmd scripts/check_repository.py
$python_cmd scripts/check_guard.py
HOOK

chmod +x "$hook"
printf 'Installed OpportunityOS pre-push checks at %s\n' "$hook"
