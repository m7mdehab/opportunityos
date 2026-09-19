"""Fail-closed hosted PostgreSQL proof runner for FR-007.

This module is an execution boundary around the repository's existing
preflight and migration-acceptance contracts.  It never prints a DSN and it
does not make a hosted migration implicit: only ``MIGRATE_STAGING`` with the
explicit acknowledgement flag can call the existing write-capable runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import db_migration_restore as db
from scripts import migration_acceptance
from scripts import production_db_preflight as preflight


MODES = ("PRECHECK", "MIGRATE_STAGING", "VERIFY_STAGING")
VALID_STATES = ("PASS", "PARTIAL", "NOT_RUN", "BLOCKED", "FAIL")


class HostedProofError(Exception):
    """A safe, operator-facing failure with no driver text attached."""


def redact_dsn(value: str) -> str:
    """Return a diagnostic DSN with the password and query values removed."""
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.hostname:
            return "<redacted>"
        user = parts.username or ""
        host = parts.hostname
        port = f":{parts.port}" if parts.port else ""
        database = parts.path or "/"
        return f"{parts.scheme}://{user}:<redacted>@{host}{port}{database}"
    except Exception:
        return "<redacted>"


def _settings():
    try:
        target = db.target_config()
    except Exception as exc:
        raise HostedProofError("target hosted database secret is required") from exc
    source = None
    try:
        source = db.config("source")
    except Exception:
        # Target-only PRECHECK is intentionally source-independent.  Source
        # credentials become mandatory only for migration/parity modes.
        pass
    if not target.get("dsn"):
        raise HostedProofError("target hosted database secret is required")
    return source, target


def identity_fingerprint(settings: dict) -> str:
    """Fingerprint host/port/database only; credentials never participate."""
    identity = "\x00".join((settings["host"].lower(), str(settings["port"]), settings["database"]))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def classify_topology(settings: dict) -> str:
    host = settings["host"].lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "local"
    if "pooler" in host or str(settings["port"]) in {"5432"}:
        # A hostname containing pooler is unambiguously a proxy.  Port 5432
        # is not rejected by itself because providers use it for direct DBs.
        if "pooler" in host:
            return "pooler"
    return "direct_or_unknown"


def live_identity(settings: dict, *, connection_factory=None) -> dict:
    """Read provider-neutral identity facts in a read-only transaction."""
    connection = None
    try:
        connection = (connection_factory or db.connect)(settings)
        cursor = connection.cursor()
        try:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT current_database(), inet_server_addr()::text, inet_server_port(), "
                "current_setting('server_version_num'), "
                "(SELECT oid::text FROM pg_database WHERE datname = current_database())"
            )
            row = cursor.fetchone()
            if not row or any(value in (None, "") for value in row):
                raise HostedProofError("live database identity could not be established")
            return {"database": str(row[0]), "server_address": str(row[1]),
                    "server_port": int(row[2]), "server_version_num": int(row[3]),
                    "database_oid": str(row[4])}
        finally:
            cursor.close()
    except HostedProofError:
        raise
    except Exception as exc:
        raise HostedProofError("live database identity could not be established") from exc
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
            connection.close()


def verify_live_distinctness(source: dict, target: dict, *, identity_factory=None):
    factory = identity_factory or live_identity
    try:
        source_live = factory(source)
        target_live = factory(target)
    except HostedProofError:
        raise
    except Exception as exc:
        raise HostedProofError("live database identity could not be established") from exc
    if source_live == target_live:
        raise HostedProofError("source and target live database identity must differ")
    return source_live, target_live


def live_identity_fingerprint(identity: dict) -> str:
    """Hash live identity facts so evidence need not expose database/network identifiers."""
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def validate_configuration(mode: str, connection_mode: str, *, acknowledge_migration: bool = False,
                           source_writes_paused: bool = False,
                           target_writes_disabled: bool = False):
    if mode not in MODES:
        raise HostedProofError("unsupported hosted proof mode")
    if connection_mode not in {"direct", "pooler", "unknown"}:
        raise HostedProofError("connection mode must be declared")
    source, target = _settings()
    if mode != "PRECHECK" and not source:
        raise HostedProofError("source hosted database secret is required for this mode")
    if source and identity_fingerprint(source) == identity_fingerprint(target):
        raise HostedProofError("source and target database identity must differ")
    if classify_topology(target) == "local":
        raise HostedProofError("hosted mode rejects a local target")
    if mode == "MIGRATE_STAGING":
        missing = []
        if not acknowledge_migration:
            missing.append("staging migration acknowledgement")
        if not source_writes_paused:
            missing.append("source writes paused acknowledgement")
        if not target_writes_disabled:
            missing.append("target writes disabled acknowledgement")
        if missing:
            raise HostedProofError("MIGRATE_STAGING requires: " + ", ".join(missing))
        if connection_mode != "direct" or classify_topology(target) == "pooler":
            raise HostedProofError("migration requires a declared direct database endpoint")
        if target.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise HostedProofError("hosted migration requires TLS")
    return source, target


def discover_alembic_head() -> str:
    """Discover the repository head dynamically; no revision is hard-coded."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        return str(ScriptDirectory.from_config(Config("alembic.ini")).get_current_head())
    except Exception as exc:
        raise HostedProofError("Alembic head discovery unavailable") from exc


def _report(mode: str, source: dict, target: dict):
    return {
        "format": 1,
        "mode": mode,
        "source_identity_fingerprint": identity_fingerprint(source) if source else None,
        "target_identity_fingerprint": identity_fingerprint(target),
        "source_host": source["host"] if source else None,
        "target_host": target["host"],
        "target_topology": classify_topology(target),
        "alembic_head": None,
        "stages": {"PRECHECK": "NOT_RUN", "MIGRATE": "NOT_RUN", "VERIFY": "NOT_RUN",
                    "CUTOVER_READY": "NOT_RUN"},
        "details": {},
        "traffic_cutover_authorized": False,
    }


def _verify_live(source: dict, target: dict):
    source_inspection = db.inspect(source)
    target_inspection = db.inspect(target)
    if source_inspection.get("alembic_revision") != target_inspection.get("alembic_revision"):
        return {"status": "FAIL", "revision": {"source": source_inspection.get("alembic_revision"),
                                                   "target": target_inspection.get("alembic_revision")}}
    from scripts import migration_baseline
    snapshots = []
    for settings in (source, target):
        connection = db.connect(settings)
        try:
            snapshots.append(migration_baseline.inspect(connection))
        finally:
            connection.close()
    differences = migration_baseline.compare(*snapshots)
    unsupported = sorted(set(migration_baseline.unsupported(snapshots[0])) |
                         set(migration_baseline.unsupported(snapshots[1])))
    return {"status": "FAIL" if differences else "PARTIAL" if unsupported else "PASS",
            "revision": {"source": source_inspection.get("alembic_revision"),
                         "target": target_inspection.get("alembic_revision")},
            "difference_paths": differences, "unsupported": unsupported}


def run(mode: str, *, connection_mode: str, output_dir: str, acknowledge_migration: bool = False,
        source_writes_paused: bool = False, target_writes_disabled: bool = False,
        allow_insecure_local: bool = False, artifact_backend: str = "postgres_payload"):
    source, target = validate_configuration(
        mode, connection_mode, acknowledge_migration=acknowledge_migration,
        source_writes_paused=source_writes_paused, target_writes_disabled=target_writes_disabled)
    report = _report(mode, source, target)
    report["alembic_head"] = discover_alembic_head()
    source_live = target_live = None
    if mode in ("MIGRATE_STAGING", "VERIFY_STAGING"):
        source_live, target_live = verify_live_distinctness(source, target)
        report["details"]["source_live_identity"] = {
            "fingerprint": live_identity_fingerprint(source_live),
            "server_version_num": source_live.get("server_version_num"),
        }
        report["details"]["target_live_identity"] = {
            "fingerprint": live_identity_fingerprint(target_live),
            "server_version_num": target_live.get("server_version_num"),
        }
    if mode == "VERIFY_STAGING":
        checked = preflight.evaluate(target, connection_mode=connection_mode,
                                     allow_insecure_local=allow_insecure_local)
        report["details"]["preflight"] = checked
        report["stages"]["PRECHECK"] = checked.get("status", "BLOCKED")
        report["stages"]["MIGRATE"] = "NOT_RUN"
        report["stages"]["CUTOVER_READY"] = "NOT_RUN"
        if not checked.get("ready"):
            report["stages"]["VERIFY"] = "BLOCKED"
            return report
        verified = _verify_live(source, target)
        report["details"]["verification"] = verified
        report["stages"]["VERIFY"] = verified["status"]
        return report
    checked = preflight.evaluate(target, connection_mode=connection_mode,
                                 allow_insecure_local=allow_insecure_local)
    report["details"]["preflight"] = checked
    report["stages"]["PRECHECK"] = checked.get("status", "BLOCKED")
    if not checked.get("ready"):
        report["stages"]["MIGRATE"] = "BLOCKED" if mode == "MIGRATE_STAGING" else "NOT_RUN"
    elif mode == "PRECHECK":
        report["stages"]["MIGRATE"] = "NOT_RUN"
        report["stages"]["VERIFY"] = "NOT_RUN"
    elif mode == "MIGRATE_STAGING":
        workspace = Path(output_dir).expanduser().resolve()
        result = migration_acceptance.run(
            workspace, connection_mode=connection_mode, artifact_backend=artifact_backend,
            confirm_restore=True, source_writes_paused=source_writes_paused,
            target_writes_disabled=target_writes_disabled,
            allow_insecure_local=allow_insecure_local)
        report["details"]["acceptance"] = result
        stages = result.get("stages", {})
        report["stages"]["MIGRATE"] = stages.get("target_migration", "FAIL")
        report["stages"]["VERIFY"] = ("PASS" if result.get("decision") == "ACCEPT" else
                                       "FAIL" if result.get("decision") == "REJECT" else "PARTIAL")
        report["stages"]["CUTOVER_READY"] = "NOT_RUN"
    if report["stages"]["VERIFY"] == "PASS" and report["stages"]["PRECHECK"] == "PASS":
        report["stages"]["CUTOVER_READY"] = "PARTIAL"
    return report


def _configured_secret_values() -> tuple[str, ...]:
    values = []
    for secret_name in ("OPOS_SOURCE_DB_URL", "OPOS_TARGET_DB_URL"):
        secret = os.environ.get(secret_name)
        if not secret:
            continue
        values.append(secret)
        try:
            password = urlsplit(secret).password
        except Exception:
            password = None
        if password:
            values.append(password)
    return tuple(dict.fromkeys(value for value in values if len(value) >= 4))


def write_evidence(report: dict, path: str):
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    configured_secrets = _configured_secret_values()

    def check(value):
        if isinstance(value, dict):
            for nested in value.values():
                check(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                check(nested)
        elif isinstance(value, str):
            if re.search(r"postgresql(?:\+[^:/\s]+)?://", value, re.I):
                raise HostedProofError("evidence contains a database URL")
            if re.search(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"']+@[^\s\"']+", value):
                raise HostedProofError("evidence contains URL credentials")
            if any(secret in value for secret in configured_secrets):
                raise HostedProofError("evidence contains configured secret")

    check(report)
    text = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    target.write_text(text, encoding="utf-8")


def exit_code(report: dict) -> int:
    states = report.get("stages", {})
    mode = report.get("mode")
    if mode == "PRECHECK":
        state = states.get("PRECHECK", "FAIL")
    elif mode == "VERIFY_STAGING":
        state = states.get("VERIFY", "FAIL")
    else:
        required = {"PRECHECK", "MIGRATE", "VERIFY"}
        values = {states.get(name, "FAIL") for name in required}
        state = ("FAIL" if "FAIL" in values else "BLOCKED" if "BLOCKED" in values or "NOT_RUN" in values
                 else "PARTIAL" if "PARTIAL" in values else "PASS")
    return {"PASS": 0, "PARTIAL": 3, "BLOCKED": 2, "FAIL": 1, "NOT_RUN": 2}[state]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--connection-mode", choices=("direct", "pooler", "unknown"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--acknowledge-staging-migration", action="store_true")
    parser.add_argument("--acknowledge-source-writes-paused", action="store_true")
    parser.add_argument("--acknowledge-target-writes-disabled", action="store_true")
    parser.add_argument("--artifact-backend", default="postgres_payload")
    args = parser.parse_args(argv)
    try:
        report = run(args.mode, connection_mode=args.connection_mode, output_dir=args.output_dir,
                     acknowledge_migration=args.acknowledge_staging_migration,
                     source_writes_paused=args.acknowledge_source_writes_paused,
                     target_writes_disabled=args.acknowledge_target_writes_disabled,
                     artifact_backend=args.artifact_backend)
        write_evidence(report, args.evidence)
    except HostedProofError as exc:
        report = {"format": 1, "mode": args.mode, "status": "BLOCKED", "reason": str(exc),
                  "stages": {"PRECHECK": "BLOCKED", "MIGRATE": "NOT_RUN", "VERIFY": "NOT_RUN",
                              "CUTOVER_READY": "NOT_RUN"}, "traffic_cutover_authorized": False}
        write_evidence(report, args.evidence)
    except Exception:
        # Driver/subprocess exceptions can contain DSNs or server text. Keep
        # the CLI and evidence contract stable even when a delegated runner
        # fails unexpectedly.
        report = {"format": 1, "mode": args.mode, "status": "FAIL", "reason": "hosted_proof_failed",
                  "stages": {"PRECHECK": "FAIL", "MIGRATE": "NOT_RUN", "VERIFY": "NOT_RUN",
                              "CUTOVER_READY": "NOT_RUN"}, "traffic_cutover_authorized": False}
        write_evidence(report, args.evidence)
    print(json.dumps(report, sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
