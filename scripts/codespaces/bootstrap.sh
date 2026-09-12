#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mkdir -p out/codespaces private

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

(
  cd web
  npm ci
  npx playwright install --with-deps chromium
)

python - <<'PY'
import os
import time
from sqlalchemy import create_engine, text

url = os.environ["OPPORTUNITYOS_DB_URL"]
deadline = time.monotonic() + 90
last = None
while time.monotonic() < deadline:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Codespaces PostgreSQL is reachable.")
        break
    except Exception as exc:  # startup probe only; surface the last error on timeout
        last = exc
        time.sleep(2)
    finally:
        engine.dispose()
else:
    raise SystemExit(f"PostgreSQL did not become reachable within 90s: {last}")
PY

alembic upgrade head

cat <<'EOF'
OpportunityOS Codespaces bootstrap complete.

The runtime intentionally does not invent Founder secrets. To start the API/Web
stack, the Codespace environment must contain:
  OPPORTUNITYOS_FOUNDER_PASSWORD
  OPPORTUNITYOS_SESSION_SECRET

The real Truth Pack, when supplied, belongs at private/truth_pack.yaml (gitignored)
or at the path named by OPPORTUNITYOS_TRUTH_PACK_PATH. Never commit it.
EOF
