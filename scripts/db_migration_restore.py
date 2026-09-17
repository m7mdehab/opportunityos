"""FR-007 PostgreSQL backup, restore, migration and verification harness.

All connection settings are injected through the environment. Errors are
deliberately redacted because driver and process exceptions may contain DSNs.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "OPOS_SOURCE_DB_URL"
TARGET = "OPOS_TARGET_DB_URL"
BASELINE = ROOT / "scripts" / "migration_baseline.py"


class HarnessError(Exception):
    pass


class ParityMismatch(HarnessError):
    pass


def config(role, environ=None):
    env = os.environ if environ is None else environ
    key = SOURCE if role == "source" else TARGET
    value = env.get(key, "")
    if not value or any(c in value for c in "\r\n\x00"):
        raise HarnessError("missing or invalid database configuration")
    parts = urlsplit(value)
    if parts.scheme not in ("postgresql", "postgresql+psycopg2"):
        raise HarnessError("PostgreSQL configuration required")
    try:
        port = parts.port or 5432
    except ValueError as exc:
        raise HarnessError("invalid database port") from exc
    queries = parse_qs(parts.query, strict_parsing=True)
    if set(queries) - {"sslmode"} or len(queries.get("sslmode", [""])) != 1:
        raise HarnessError("unsupported database options")
    sslmode = queries.get("sslmode", ["prefer"])[0]
    if sslmode not in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
        raise HarnessError("invalid SSL mode")
    if not parts.hostname or not parts.username or not parts.password or not parts.path.startswith("/"):
        raise HarnessError("incomplete database configuration")
    database = unquote(parts.path[1:])
    if not database or "/" in database or "\x00" in database:
        raise HarnessError("invalid database name")
    return {"dsn": value, "driver_dsn": value.replace("postgresql+psycopg2://", "postgresql://", 1),
            "host": parts.hostname, "port": str(port),
            "user": unquote(parts.username), "password": unquote(parts.password),
            "database": database, "sslmode": sslmode}


def target_config(environ=None):
    source = config("source", environ)
    target = config("target", environ)
    identity = lambda item: (item["host"].lower(), item["port"], item["database"])
    if identity(source) == identity(target):
        raise HarnessError("source and target database must be distinct")
    return target


def pg_environment(settings, environ=None):
    """Connection details stay in child environment, never command arguments."""
    env = dict(os.environ if environ is None else environ)
    for key in (SOURCE, TARGET, "OPPORTUNITYOS_DB_URL", "PGSERVICE", "PGPASSFILE", "PGOPTIONS",
                "PGHOSTADDR", "PGSERVICEFILE", "PGSYSCONFDIR"):
        env.pop(key, None)
    env.update(PGHOST=settings["host"], PGPORT=settings["port"],
               PGUSER=settings["user"], PGPASSWORD=settings["password"],
               PGDATABASE=settings["database"], PGSSLMODE=settings["sslmode"],
               PGCONNECT_TIMEOUT="10")
    return env


def require_tool(name):
    executable = shutil.which(name)
    if not executable:
        raise HarnessError(f"required tool unavailable: {name}")
    return executable


def run_command(argv, env):
    # stdout/stderr are never forwarded: pg_dump/pg_restore/alembic may echo
    # connection settings, object names, or private row content on failure.
    result = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False, shell=False)
    if result.returncode:
        raise HarnessError("database command failed")


def connect(settings):
    try:
        import psycopg2
    except ImportError as exc:
        raise HarnessError("psycopg2 unavailable") from exc
    return psycopg2.connect(settings["driver_dsn"], connect_timeout=10)


def inspect(settings, *, require_empty=False):
    connection = connect(settings)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT 1")
            if cursor.fetchone()[0] != 1:
                raise HarnessError("database readiness check failed")
            cursor.execute("SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
            tables = int(cursor.fetchone()[0])
            if require_empty and tables:
                raise HarnessError("target schema is not empty")
            cursor.execute("SELECT to_regclass('public.alembic_version')")
            if cursor.fetchone()[0] is None:
                revision = None
            else:
                cursor.execute("SELECT version_num FROM public.alembic_version ORDER BY version_num")
                revisions = [row[0] for row in cursor.fetchall()]
                if len(revisions) > 1:
                    raise HarnessError("multiple Alembic revisions")
                revision = revisions[0] if revisions else None
                if revision is not None and (not isinstance(revision, str) or
                                             not revision.replace("_", "").replace("-", "").isalnum()):
                    raise HarnessError("invalid Alembic revision")
            cursor.execute("ROLLBACK")
            return {"ready": True, "alembic_revision": revision, "table_count": tables}
        finally:
            cursor.close()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def backup(settings, destination):
    path = Path(destination).expanduser().resolve()
    if path.exists() or not path.parent.is_dir():
        raise HarnessError("backup destination must be a new file in an existing directory")
    tool = require_tool("pg_dump")
    argv = [tool, "--format=custom", "--schema=public", "--no-owner", "--no-privileges",
            "--file", str(path), "--dbname", settings["database"]]
    try:
        run_command(argv, pg_environment(settings))
    except Exception:
        if path.exists():
            path.unlink()
        raise
    if not path.is_file() or path.stat().st_size == 0:
        raise HarnessError("backup file missing or empty")


def restore(settings, archive, *, confirmed=False):
    if not confirmed:
        raise HarnessError("explicit target restore confirmation required")
    path = Path(archive).expanduser().resolve()
    if not path.is_file():
        raise HarnessError("backup archive missing")
    inspect(settings, require_empty=True)
    tool = require_tool("pg_restore")
    # No --clean or --create: an existing database/schema is never replaced.
    argv = [tool, "--exit-on-error", "--single-transaction", "--no-owner",
            "--no-privileges", "--dbname", settings["database"], str(path)]
    run_command(argv, pg_environment(settings))


def migrate(settings):
    if not (ROOT / "alembic.ini").is_file() or not (ROOT / "storage" / "migrations" / "env.py").is_file():
        raise HarnessError("repository migration path unavailable")
    env = dict(os.environ)
    env.pop(SOURCE, None)
    env.pop(TARGET, None)
    env["OPPORTUNITYOS_DB_URL"] = settings["dsn"]
    run_command([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], env)


def baseline_handoff(operation, settings=None, baseline=None, candidate=None, output=None):
    if not BASELINE.is_file():
        raise HarnessError("migration baseline module unavailable; integrate its branch first")
    env = dict(os.environ)
    env.pop(SOURCE, None)
    env.pop(TARGET, None)
    if operation == "snapshot":
        if settings is None or output is None:
            raise HarnessError("snapshot configuration incomplete")
        env["OPPORTUNITYOS_DB_URL"] = settings["dsn"]
        path = Path(output).expanduser().resolve()
        if path.exists() or not path.parent.is_dir():
            raise HarnessError("snapshot destination must be a new file")
        with path.open("x", encoding="utf-8") as stream:
            result = subprocess.run([sys.executable, str(BASELINE), "snapshot"],
                                    cwd=ROOT, env=env, stdout=stream,
                                    stderr=subprocess.DEVNULL, check=False, shell=False)
        if result.returncode:
            path.unlink()
            raise HarnessError("baseline snapshot failed")
    elif operation == "compare":
        if not baseline or not candidate:
            raise HarnessError("two snapshots required")
        result = subprocess.run([sys.executable, str(BASELINE), "compare", str(Path(baseline).resolve()),
                                 str(Path(candidate).resolve())], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                check=False, shell=False)
        if result.returncode == 1:
            raise ParityMismatch("migration parity mismatch")
        if result.returncode:
            raise HarnessError("baseline comparison failed")
    else:
        raise HarnessError("unsupported baseline operation")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("inspect")
    sub.add_parser("migrate")
    export = sub.add_parser("backup")
    export.add_argument("--destination", required=True)
    load = sub.add_parser("restore")
    load.add_argument("--archive", required=True)
    load.add_argument("--confirm-target-restore", action="store_true")
    sub.add_parser("verify")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--role", choices=("source", "target"), required=True)
    snap.add_argument("--output", required=True)
    parity = sub.add_parser("parity")
    parity.add_argument("--baseline", required=True)
    parity.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            settings = target_config()
            result = {"source": inspect(config("source")), "target": inspect(settings)}
        elif args.operation == "migrate":
            settings = target_config()
            migrate(settings)
            result = {"target": inspect(settings)}
        elif args.operation == "backup":
            backup(config("source"), args.destination)
            result = {"backup": "created"}
        elif args.operation == "restore":
            settings = target_config()
            restore(settings, args.archive, confirmed=args.confirm_target_restore)
            result = {"target": inspect(settings)}
        elif args.operation == "verify":
            result = {"target": inspect(target_config())}
            if result["target"]["alembic_revision"] is None:
                raise HarnessError("target Alembic revision unavailable")
        elif args.operation == "snapshot":
            settings = config("source") if args.role == "source" else target_config()
            baseline_handoff("snapshot", settings, output=args.output)
            result = {"snapshot": "created"}
        else:
            baseline_handoff("compare", baseline=args.baseline, candidate=args.candidate)
            result = {"parity": "pass"}
        print(json.dumps({"status": "ok", **result}, sort_keys=True))
        return 0
    except ParityMismatch as exc:
        print(json.dumps({"status": "mismatch", "reason": str(exc)}), file=sys.stderr)
        return 1
    except HarnessError as exc:
        # These are fixed, locally constructed messages, never driver errors.
        print(json.dumps({"status": "error", "reason": str(exc)}), file=sys.stderr)
        return 3 if "baseline module unavailable" in str(exc) else 2
    except (Exception, KeyboardInterrupt):
        print('{"status":"error","reason":"database operation failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
