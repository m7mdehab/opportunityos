"""Compare the live Alembic heads with this checkout's migration heads."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]


def repository_migration_heads(root: Path = ROOT) -> tuple[str, ...]:
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "storage/migrations"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def migration_heads_match(current_heads: Any, expected_heads: tuple[str, ...] | None = None) -> bool:
    current = tuple(sorted(str(head) for head in current_heads))
    expected = expected_heads or repository_migration_heads()
    return bool(expected) and current == tuple(sorted(expected))


def verify_connection_head(connection, *, expected_heads: tuple[str, ...] | None = None) -> dict[str, tuple[str, ...]]:
    current = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
    expected = expected_heads or repository_migration_heads()
    if not migration_heads_match(current, expected):
        raise RuntimeError("database migration heads differ from repository heads")
    return {"current_heads": current, "expected_heads": tuple(sorted(expected))}


def main() -> int:
    raw = os.environ.get("OPOS_TARGET_DB_URL") or os.environ.get("OPPORTUNITYOS_DB_URL")
    if not raw:
        print(json.dumps({"status": "error", "error": "database_url_missing"}))
        return 2
    from storage.engine import get_production_db_url

    engine = create_engine(
        get_production_db_url(raw), pool_size=1, max_overflow=0, pool_pre_ping=True
    )
    try:
        with engine.connect() as connection:
            result = verify_connection_head(connection)
        print(json.dumps({"status": "ok", **result}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error_class": type(exc).__name__}, sort_keys=True))
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
