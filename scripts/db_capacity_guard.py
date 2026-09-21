"""Fail-closed PostgreSQL capacity/read-only guard for heavy worker work.

The module is intentionally provider-neutral.  It reports only numeric
capacity and sanitized transaction state; DSNs and database contents never
enter output.  Workers can call :func:`assert_heavy_work_allowed` before
enqueueing a poll/evaluation wave.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text

WARN_BYTES = 350 * 1024 * 1024
BLOCK_BYTES = 425 * 1024 * 1024
TARGET_BYTES = 400 * 1024 * 1024


class CapacityBlocked(RuntimeError):
    """A heavy operation cannot safely start under the current DB posture."""


@dataclass(frozen=True)
class CapacitySnapshot:
    database_size_bytes: int
    read_only: bool
    in_recovery: bool
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "database_size_bytes": self.database_size_bytes,
            "read_only": self.read_only,
            "in_recovery": self.in_recovery,
            "status": self.status,
            "target_bytes": TARGET_BYTES,
            "warning_bytes": WARN_BYTES,
            "block_bytes": BLOCK_BYTES,
        }


def inspect_connection(connection) -> CapacitySnapshot:
    size = int(connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    read_only = bool(connection.execute(text("SELECT current_setting('default_transaction_read_only') = 'on'")).scalar_one())
    in_recovery = bool(connection.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
    if read_only or in_recovery:
        status = "READ_ONLY"
    elif size > BLOCK_BYTES:
        status = "BLOCKED_CAPACITY"
    elif size > WARN_BYTES:
        status = "WARN_CAPACITY"
    else:
        status = "OK"
    return CapacitySnapshot(size, read_only, in_recovery, status)


def assert_heavy_work_allowed(connection) -> CapacitySnapshot:
    snapshot = inspect_connection(connection)
    if snapshot.read_only or snapshot.in_recovery:
        raise CapacityBlocked("database is read-only; heavy work is blocked")
    if snapshot.database_size_bytes > BLOCK_BYTES:
        raise CapacityBlocked("database exceeds the heavy-work capacity guard")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the sanitized DB capacity guard")
    parser.add_argument("--dsn-env", default="OPOS_TARGET_DB_URL")
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"missing required environment variable {args.dsn_env}")
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            print(json.dumps(inspect_connection(connection).as_dict(), sort_keys=True))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
