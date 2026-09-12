#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT/out/codespaces"
mkdir -p "$RUN_DIR"
cd "$ROOT"

required=(OPPORTUNITYOS_DB_URL OPPORTUNITYOS_FOUNDER_PASSWORD OPPORTUNITYOS_SESSION_SECRET)
missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if ((${#missing[@]})); then
  printf 'OpportunityOS Codespaces runtime not started: missing %s\n' "${missing[*]}"
  printf 'Add the missing values as Codespaces secrets, then run: bash scripts/codespaces/start.sh\n'
  exit 0
fi

if [[ -z "${OPPORTUNITYOS_TRUTH_PACK_PATH:-}" && -f "$ROOT/private/truth_pack.yaml" ]]; then
  export OPPORTUNITYOS_TRUTH_PACK_PATH="$ROOT/private/truth_pack.yaml"
fi

alembic upgrade head

is_running() {
  local name="$1" pid_file="$RUN_DIR/$1.pid"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  kill -0 "$pid" 2>/dev/null
}

start_process() {
  local name="$1" command="$2"
  if is_running "$name"; then
    printf '%s already running (pid %s).\n' "$name" "$(cat "$RUN_DIR/$name.pid")"
    return
  fi
  rm -f "$RUN_DIR/$name.pid"
  nohup bash -lc "cd '$ROOT' && exec $command" >"$RUN_DIR/$name.log" 2>&1 < /dev/null &
  echo "$!" >"$RUN_DIR/$name.pid"
  printf 'started %s (pid %s)\n' "$name" "$!"
}

wait_port() {
  local label="$1" host="$2" port="$3" timeout="$4"
  python - "$label" "$host" "$port" "$timeout" <<'PY'
import socket
import sys
import time
label, host, port_s, timeout_s = sys.argv[1:]
port, timeout = int(port_s), float(timeout_s)
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1):
            print(f"{label} ready on {host}:{port}")
            raise SystemExit(0)
    except OSError:
        time.sleep(0.5)
raise SystemExit(f"{label} did not listen on {host}:{port} within {timeout:g}s")
PY
}

start_process worker "python -m worker --schedule"
start_process api "python -m uvicorn api.app:app --host 0.0.0.0 --port 8000"
wait_port "FastAPI" 127.0.0.1 8000 60
start_process web "cd web && npm run dev -- --hostname 0.0.0.0 -p 3000"
wait_port "Founder Web Alpha" 127.0.0.1 3000 120

cat <<'EOF'
OpportunityOS Founder Alpha is running.
- Web: forwarded Codespaces port 3000 (GitHub keeps forwarded ports private by default).
- API: port 8000, used by the web proxy and available for diagnostics.
- Worker: scheduler + queue runner active.
- Logs/PIDs: out/codespaces/ (gitignored).

If private/truth_pack.yaml is absent, the API remains fail-safe for Truth-Pack-dependent
artifact operations; do not substitute fixture data for the Founder pack.
EOF
