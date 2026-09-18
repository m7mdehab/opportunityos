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
        source = db.config("source")
        target = db.target_config()
    except Exception as exc:
        raise HostedProofError("source and target hosted database secrets are required") from exc
    if not source.get("dsn") or not target.get("dsn"):
        raise HostedProofError("source and target hosted database secrets are required")
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


def validate_configuration(mode: str, connection_mode: str, *, confirm_staging: bool = False):
    if mode not in MODES:
        raise HostedProofError("unsupported hosted proof mode")
    if connection_mode not in {"direct", "pooler", "unknown"}:
        raise HostedProofError("connection mode must be declared")
    source, target = _settings()
    if identity_fingerprint(source) == identity_fingerprint(target):
        raise HostedProofError("source and target database identity must differ")
    if classify_topology(target) == "local":
        raise HostedProofError("hosted mode rejects a local target")
    if mode == "MIGRATE_STAGING":
        if not confirm_staging:
            raise HostedProofError("MIGRATE_STAGING requires explicit staging acknowledgement")
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
        "source_identity_fingerprint": identity_fingerprint(source),
        "target_identity_fingerprint": identity_fingerprint(target),
        "source_host": source["host"],
        "target_host": target["host"],
        "target_topology": classify_topology(target),
        "alembic_head": None,
        "stages": {"PRECHECK": "NOT_RUN", "MIGRATE": "NOT_RUN", "VERIFY": "NOT_RUN",
                    "CUTOVER_READY": "NOT_RUN"},
        "details": {},
        "traffic_cutover_authorized": False,
    }


def run(mode: str, *, connection_mode: str, output_dir: str, confirm_staging: bool = False,
        allow_insecure_local: bool = False, artifact_backend: str = "postgres_payload"):
    source, target = validate_configuration(mode, connection_mode, confirm_staging=confirm_staging)
    report = _report(mode, source, target)
    report["alembic_head"] = discover_alembic_head()
    report["details"]["source_dsn"] = redact_dsn(source["dsn"])
    report["details"]["target_dsn"] = redact_dsn(target["dsn"])
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
            confirm_restore=True, source_writes_paused=True, target_writes_disabled=True,
            allow_insecure_local=allow_insecure_local)
        report["details"]["acceptance"] = result
        stages = result.get("stages", {})
        report["stages"]["MIGRATE"] = stages.get("target_migration", "FAIL")
        report["stages"]["VERIFY"] = ("PASS" if result.get("decision") == "ACCEPT" else
                                       "FAIL" if result.get("decision") == "REJECT" else "PARTIAL")
        report["stages"]["CUTOVER_READY"] = "NOT_RUN"
    else:  # VERIFY_STAGING: inspect the prior acceptance artifact, never write.
        acceptance_path = Path(output_dir).expanduser().resolve() / "acceptance.json"
        if not acceptance_path.is_file():
            report["stages"]["VERIFY"] = "BLOCKED"
            report["details"]["verify"] = {"reason": "acceptance_report_required"}
        else:
            try:
                prior = json.loads(acceptance_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise HostedProofError("acceptance report is unavailable or invalid") from exc
            report["details"]["acceptance"] = prior
            report["stages"]["VERIFY"] = "PASS" if prior.get("decision") == "ACCEPT" else "FAIL"
    if report["stages"]["VERIFY"] == "PASS" and report["stages"]["PRECHECK"] == "PASS":
        report["stages"]["CUTOVER_READY"] = "PARTIAL"
    return report


def write_evidence(report: dict, path: str):
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Reports contain only allowlisted metadata and nested existing reports.
    text = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if "postgresql://" in text and "<redacted>" not in text:
        raise HostedProofError("evidence redaction invariant failed")
    target.write_text(text, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--connection-mode", choices=("direct", "pooler", "unknown"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--confirm-staging-migration", action="store_true")
    parser.add_argument("--artifact-backend", default="postgres_payload")
    args = parser.parse_args(argv)
    try:
        report = run(args.mode, connection_mode=args.connection_mode, output_dir=args.output_dir,
                     confirm_staging=args.confirm_staging_migration, artifact_backend=args.artifact_backend)
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
    states = set(report.get("stages", {}).values())
    return 0 if states == {"PASS"} else 1 if "FAIL" in states else 2


if __name__ == "__main__":
    raise SystemExit(main())
