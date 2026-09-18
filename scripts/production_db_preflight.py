"""Read-only PostgreSQL target preflight for FR-007 migration rehearsals.

Output is an allowlist of operational facts. Driver errors, DSNs, object names,
and server-provided text are never forwarded to stdout or stderr.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import db_migration_restore as db


CHECKS = ("version", "tls", "connection_mode", "extensions", "privileges",
          "schema_ownership", "alembic", "target_empty", "transaction",
          "session_settings", "timeouts", "database_size")
MIN_SERVER_VERSION = 140000
REQUIRED_EXTENSIONS = frozenset()  # 0001-0006 use built-in PostgreSQL features.


def _state(ok, *, blocked=False):
    return "PASS" if ok else "BLOCKED" if blocked else "PARTIAL"


def evaluate(settings, *, connection_mode=None, allow_insecure_local=False,
             connection_factory=None):
    """Probe target with one read-only transaction; never run DDL or DML."""
    result = {"format": 1, "checks": {name: "NOT_RUN" for name in CHECKS},
              "details": {}, "status": "BLOCKED", "ready": False}
    local = settings["host"].lower() in ("localhost", "127.0.0.1", "::1")
    if allow_insecure_local and not local:
        result["checks"]["tls"] = "BLOCKED"
        result["details"]["tls"] = "local_override_requires_loopback_host"
        return result
    if connection_mode not in ("direct", "pooler", "unknown"):
        result["checks"]["connection_mode"] = "BLOCKED"
        result["details"]["connection_mode"] = "explicit_direct_connection_declaration_required"
        return result
    connection = None
    try:
        connection = (connection_factory or db.connect)(settings)
        cursor = connection.cursor()
        try:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT current_setting('server_version_num')::integer, "
                           "current_database(), current_user, pg_backend_pid()")
            version, database, user, backend_pid = cursor.fetchone()
            result["details"]["version"] = {"server_version_num": int(version)}
            result["checks"]["version"] = _state(int(version) >= MIN_SERVER_VERSION, blocked=True)

            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = %s", (backend_pid,))
            row = cursor.fetchone()
            tls_active = bool(row[0]) if row else False
            ssl_required = settings["sslmode"] in ("require", "verify-ca", "verify-full")
            result["checks"]["tls"] = _state(
                tls_active and ssl_required or allow_insecure_local and local, blocked=True)
            result["details"]["tls"] = {"active": tls_active, "required_by_dsn": ssl_required,
                                         "local_exception": bool(allow_insecure_local and local)}

            # Endpoint topology cannot be established reliably from SQL alone.
            # An explicit direct declaration permits rehearsal but remains
            # partial until independently checked in the provider control plane.
            result["checks"]["connection_mode"] = ("PARTIAL" if connection_mode == "direct" else "BLOCKED")
            result["details"]["connection_mode"] = {
                "declared": connection_mode, "provider_verified": False}

            cursor.execute("SELECT extname FROM pg_extension")
            installed = {row[0] for row in cursor.fetchall()}
            missing = sorted(REQUIRED_EXTENSIONS - installed)
            result["checks"]["extensions"] = _state(not missing, blocked=True)
            result["details"]["extensions"] = {"required": sorted(REQUIRED_EXTENSIONS),
                                                  "missing": missing}

            cursor.execute("SELECT has_database_privilege(current_user, current_database(), 'CREATE'), "
                           "has_schema_privilege(current_user, 'public', 'USAGE'), "
                           "has_schema_privilege(current_user, 'public', 'CREATE')")
            privileges = tuple(bool(x) for x in cursor.fetchone())
            # Current migrations create objects in an existing public schema;
            # database-level CREATE is informational, not a required grant.
            result["checks"]["privileges"] = _state(all(privileges[1:]), blocked=True)
            result["details"]["privileges"] = dict(zip(
                ("database_create", "public_usage", "public_create"), privileges))

            cursor.execute("SELECT pg_get_userbyid(nspowner) = current_user "
                           "FROM pg_namespace WHERE nspname = 'public'")
            owned = cursor.fetchone()
            result["checks"]["schema_ownership"] = "PASS" if owned and owned[0] else "PARTIAL"
            result["details"]["schema_ownership"] = {"public_owned_by_current_user": bool(owned and owned[0])}

            cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') "
                           "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=c.oid "
                           "AND d.deptype='e')")
            object_count = int(cursor.fetchone()[0])
            result["checks"]["target_empty"] = _state(object_count == 0, blocked=True)
            result["details"]["target_empty"] = {"existing_object_count": object_count}

            cursor.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            has_alembic = bool(cursor.fetchone()[0])
            if has_alembic:
                cursor.execute("SELECT count(*) FROM public.alembic_version")
                revision_rows = int(cursor.fetchone()[0])
            else:
                revision_rows = 0
            result["checks"]["alembic"] = _state(not has_alembic, blocked=True)
            result["details"]["alembic"] = {"table_present": has_alembic,
                                              "revision_row_count": revision_rows}
            result["checks"]["transaction"] = "PASS"
            result["details"]["transaction"] = {"repeatable_read_read_only": True}

            cursor.execute("SELECT current_schemas(false), current_setting('TimeZone'), "
                           "current_setting('standard_conforming_strings'), "
                           "current_setting('row_security'), "
                           "current_setting('default_transaction_read_only')")
            schemas, timezone, strings, row_security, default_read_only = cursor.fetchone()
            settings_ok = ("public" in schemas and timezone.upper() in ("UTC", "ETC/UTC")
                           and strings == "on" and default_read_only == "off")
            result["checks"]["session_settings"] = _state(settings_ok, blocked=True)
            result["details"]["session_settings"] = {
                "public_in_search_path": "public" in schemas, "timezone_utc": timezone.upper() in ("UTC", "ETC/UTC"),
                "standard_conforming_strings": strings == "on", "row_security_on": row_security == "on",
                "default_transaction_read_only": default_read_only == "on"}

            cursor.execute("SELECT name, setting, unit FROM pg_settings "
                           "WHERE name IN ('statement_timeout','lock_timeout') ORDER BY name")
            timeout_rows = {name: (int(value), unit) for name, value, unit in cursor.fetchall()}
            def millis(item):
                value, unit = item
                return value * {"ms": 1, "s": 1000, "min": 60000}.get(unit, -1)
            timeout_ms = {name: millis(timeout_rows[name]) for name in
                          ("statement_timeout", "lock_timeout") if name in timeout_rows}
            suitable = (len(timeout_ms) == 2 and all(value == 0 or value >= limit for
                        (name, value), limit in zip(sorted(timeout_ms.items()), (5000, 30000))))
            result["checks"]["timeouts"] = _state(suitable, blocked=True)
            result["details"]["timeouts"] = timeout_ms

            try:
                cursor.execute("SAVEPOINT opos_size_probe")
                cursor.execute("SELECT pg_database_size(current_database())")
                size = int(cursor.fetchone()[0])
                cursor.execute("RELEASE SAVEPOINT opos_size_probe")
                result["checks"]["database_size"] = "PASS"
                result["details"]["database_size"] = {"bytes": size}
            except Exception:
                cursor.execute("ROLLBACK TO SAVEPOINT opos_size_probe")
                result["checks"]["database_size"] = "PARTIAL"
                result["details"]["database_size"] = {"availability": "unsupported"}
            connection.rollback()
        finally:
            cursor.close()
    except Exception:
        if connection is not None:
            connection.rollback()
        result["checks"]["transaction"] = "BLOCKED"
        result["details"]["transaction"] = "connection_or_probe_failed"
    finally:
        if connection is not None:
            connection.close()
    statuses = set(result["checks"].values())
    result["ready"] = not ("BLOCKED" in statuses or "FAIL" in statuses or "NOT_RUN" in statuses)
    result["status"] = "BLOCKED" if not result["ready"] else "PARTIAL" if "PARTIAL" in statuses else "PASS"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-mode", choices=("direct", "pooler", "unknown"), required=True)
    parser.add_argument("--allow-insecure-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate(db.target_config(), connection_mode=args.connection_mode,
                          allow_insecure_local=args.allow_insecure_local)
    except Exception:
        report = {"status": "BLOCKED", "reason": "configuration_failed"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3 if report["status"] == "PARTIAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
