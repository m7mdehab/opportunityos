"""FR-007 PostgreSQL backup, restore, migration and verification harness.

All connection settings are injected through the environment. Errors are
deliberately redacted because driver and process exceptions may contain DSNs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re
from urllib.parse import parse_qs, unquote, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "OPOS_SOURCE_DB_URL"
TARGET = "OPOS_TARGET_DB_URL"
BASELINE = ROOT / "scripts" / "migration_baseline.py"


class HarnessError(Exception):
    pass


class ParityMismatch(HarnessError):
    pass


class PartialParity(HarnessError):
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


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_manifest(archive, revision, *, version, commit, created_at=None):
    path = Path(archive)
    if not path.is_file() or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise HarnessError("backup or application revision unavailable")
    if not re.fullmatch(r"pg_dump \(PostgreSQL\) [0-9][A-Za-z0-9.()+ -]{0,120}", version):
        raise HarnessError("invalid backup tool version")
    return {"format": 1, "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "archive_format": "pg_dump_custom", "expected_restore_type": "fresh_public_schema",
            "schema": "public", "alembic_revision": revision,
            "pg_dump_version": version, "application_commit": commit,
            "compressed_size_bytes": path.stat().st_size, "uncompressed_size_bytes": None,
            "sha256": file_sha256(path)}


def write_backup_manifest(archive, manifest):
    path = Path(str(archive) + ".manifest.json")
    if path.exists():
        raise HarnessError("backup manifest already exists")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    return path


def verify_backup(archive, manifest_path):
    path = Path(archive).expanduser().resolve()
    try:
        with Path(manifest_path).open(encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError) as exc:
        raise HarnessError("backup manifest unavailable or invalid") from exc
    if (not isinstance(manifest, dict) or manifest.get("format") != 1
            or manifest.get("archive_format") != "pg_dump_custom"
            or manifest.get("expected_restore_type") != "fresh_public_schema"
            or manifest.get("schema") != "public"
            or not isinstance(manifest.get("compressed_size_bytes"), int)
            or not isinstance(manifest.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"])):
        raise HarnessError("backup manifest contract mismatch")
    if (not path.is_file() or path.stat().st_size != manifest["compressed_size_bytes"]
            or file_sha256(path) != manifest["sha256"]):
        raise HarnessError("backup integrity mismatch")
    return manifest


def tool_version(name):
    executable = require_tool(name)
    result = subprocess.run([executable, "--version"], cwd=ROOT, env=pg_environment(config("source")),
                            capture_output=True, text=True, check=False, shell=False)
    if result.returncode:
        raise HarnessError("backup tool version unavailable")
    return result.stdout.strip()


def application_commit():
    tool = require_tool("git")
    result = subprocess.run([tool, "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=False, shell=False)
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", result.stdout.strip()):
        raise HarnessError("application revision unavailable")
    return result.stdout.strip()


def restore(settings, archive, *, manifest=None, confirmed=False):
    if not confirmed:
        raise HarnessError("explicit target restore confirmation required")
    if manifest is None:
        raise HarnessError("backup manifest required")
    path = Path(archive).expanduser().resolve()
    verify_backup(path, manifest)
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
        if result.returncode == 3:
            raise PartialParity("unsupported parity concepts remain")
        if result.returncode:
            raise HarnessError("baseline comparison failed")
    else:
        raise HarnessError("unsupported baseline operation")


def parity_live(source, target):
    """Compare two independent read-only snapshots without writing private files."""
    if not BASELINE.is_file():
        raise HarnessError("migration baseline module unavailable; integrate its branch first")
    from scripts import migration_baseline
    snapshots = []
    for settings in (source, target):
        connection = connect(settings)
        try:
            snapshots.append(migration_baseline.inspect(connection))
        finally:
            connection.close()
    return {"differences": migration_baseline.compare(*snapshots),
            "unsupported": sorted(set(migration_baseline.unsupported(snapshots[0])) |
                                  set(migration_baseline.unsupported(snapshots[1])))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("inspect")
    sub.add_parser("migrate")
    export = sub.add_parser("backup")
    export.add_argument("--destination", required=True)
    check = sub.add_parser("verify-backup")
    check.add_argument("--archive", required=True)
    check.add_argument("--manifest", required=True)
    load = sub.add_parser("restore")
    load.add_argument("--archive", required=True)
    load.add_argument("--manifest", required=True)
    load.add_argument("--confirm-target-restore", action="store_true")
    sub.add_parser("verify")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--role", choices=("source", "target"), required=True)
    snap.add_argument("--output", required=True)
    parity = sub.add_parser("parity")
    parity.add_argument("--baseline", required=True)
    parity.add_argument("--candidate", required=True)
    sub.add_parser("parity-live")
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
            settings = config("source")
            source_revision = inspect(settings)["alembic_revision"]
            if source_revision is None:
                raise HarnessError("source Alembic revision unavailable")
            version = tool_version("pg_dump")
            commit = application_commit()
            backup(settings, args.destination)
            try:
                manifest = backup_manifest(args.destination, source_revision, version=version, commit=commit)
                write_backup_manifest(args.destination, manifest)
            except Exception:
                Path(args.destination).unlink(missing_ok=True)
                raise
            result = {"backup": "created", "manifest": "created"}
        elif args.operation == "verify-backup":
            verify_backup(args.archive, args.manifest)
            result = {"backup_integrity": "pass"}
        elif args.operation == "restore":
            settings = target_config()
            restore(settings, args.archive, manifest=args.manifest, confirmed=args.confirm_target_restore)
            result = {"target": inspect(settings)}
        elif args.operation == "verify":
            result = {"target": inspect(target_config())}
            if result["target"]["alembic_revision"] is None:
                raise HarnessError("target Alembic revision unavailable")
        elif args.operation == "snapshot":
            settings = config("source") if args.role == "source" else target_config()
            baseline_handoff("snapshot", settings, output=args.output)
            result = {"snapshot": "created"}
        elif args.operation == "parity":
            baseline_handoff("compare", baseline=args.baseline, candidate=args.candidate)
            result = {"parity": "pass"}
        else:
            parity_result = parity_live(config("source"), target_config())
            if parity_result["differences"]:
                print(json.dumps({"status": "mismatch", **parity_result,
                                  "summary": f"Parity failed: {len(parity_result['differences'])} structural differences"},
                                 sort_keys=True))
                return 1
            if parity_result["unsupported"]:
                print(json.dumps({"status": "partial", **parity_result,
                                  "summary": f"Supported checks matched; {len(parity_result['unsupported'])} concepts unsupported"},
                                 sort_keys=True))
                return 3
            result = {"parity": "pass", "summary": "Parity passed: all supported structural checks matched"}
        print(json.dumps({"status": "ok", **result}, sort_keys=True))
        return 0
    except ParityMismatch as exc:
        print(json.dumps({"status": "mismatch", "reason": str(exc)}), file=sys.stderr)
        return 1
    except PartialParity as exc:
        print(json.dumps({"status": "partial", "reason": str(exc)}), file=sys.stderr)
        return 3
    except HarnessError as exc:
        # These are fixed, locally constructed messages, never driver errors.
        print(json.dumps({"status": "error", "reason": str(exc)}), file=sys.stderr)
        return 3 if "baseline module unavailable" in str(exc) else 2
    except (Exception, KeyboardInterrupt):
        print('{"status":"error","reason":"database operation failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
