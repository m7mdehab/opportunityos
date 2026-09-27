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

MIB = 1024 * 1024
PREFERRED_BYTES = 300 * MIB
WARN_BYTES = 350 * MIB
BLOCK_BYTES = 400 * MIB
HEAVY_WORK_PAUSE_BYTES = BLOCK_BYTES
HARD_STOP_BYTES = 425 * MIB
PROVIDER_LIMIT_BYTES = 500 * MIB


class CapacityBlocked(RuntimeError):
    """A heavy operation cannot safely start under the current DB posture."""


@dataclass(frozen=True)
class CapacitySnapshot:
    database_size_bytes: int
    read_only: bool
    in_recovery: bool
    status: str

    @property
    def pauses_heavy_work(self) -> bool:
        return (
            self.read_only
            or self.in_recovery
            or self.database_size_bytes >= BLOCK_BYTES
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "database_size_bytes": self.database_size_bytes,
            "read_only": self.read_only,
            "in_recovery": self.in_recovery,
            "status": self.status,
            "preferred_bytes": PREFERRED_BYTES,
            "warning_bytes": WARN_BYTES,
            "block_bytes": BLOCK_BYTES,
            "hard_stop_bytes": HARD_STOP_BYTES,
            "provider_limit_bytes": PROVIDER_LIMIT_BYTES,
        }


def inspect_connection(connection) -> CapacitySnapshot:
    size = int(connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    read_only = bool(connection.execute(text(
        "SELECT current_setting('default_transaction_read_only') = 'on' "
        "OR current_setting('transaction_read_only') = 'on'"
    )).scalar_one())
    in_recovery = bool(connection.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
    if read_only:
        status = "READ_ONLY"
    elif in_recovery:
        status = "IN_RECOVERY"
    elif size >= HARD_STOP_BYTES:
        status = "HARD_STOP_CAPACITY"
    elif size >= BLOCK_BYTES:
        status = "HEAVY_WORK_PAUSED"
    elif size >= WARN_BYTES:
        status = "WARN_CAPACITY"
    elif size >= PREFERRED_BYTES:
        status = "MONITOR_CAPACITY"
    else:
        status = "NORMAL"
    return CapacitySnapshot(size, read_only, in_recovery, status)


def assert_heavy_work_allowed(connection) -> CapacitySnapshot:
    snapshot = inspect_connection(connection)
    if snapshot.read_only or snapshot.in_recovery:
        raise CapacityBlocked("database is read-only or in recovery; heavy work is paused")
    if snapshot.database_size_bytes >= HARD_STOP_BYTES:
        raise CapacityBlocked("database reached the OpportunityOS 425 MiB internal hard stop")
    if snapshot.database_size_bytes >= BLOCK_BYTES:
        raise CapacityBlocked("heavy work is paused at the OpportunityOS 400 MiB boundary")
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
