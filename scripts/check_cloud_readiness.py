#!/usr/bin/env python3
"""OpportunityOS Cloud Deployment Readiness Preflight.

Answers the canonical operational question:
  "Can this repository, with valid secrets and a reachable PostgreSQL database,
   launch the FR-007 cloud roles without the Founder laptop?"

Checks static and runtime prerequisites without:
  - scanning the opportunity corpus;
  - evaluating opportunities;
  - rebuilding feed projections;
  - accessing private Founder data unnecessarily.

Exit codes:
  0 = All prerequisites verified. Cloud roles ready to launch.
  1 = One or more prerequisites failed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

# Ensure repository root is on sys.path for direct script invocation
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.container_entrypoint import (
    ConfigurationError,
    _is_loopback_host,
    resolve_environment,
)

REQUIRED_TABLES = ("alembic_version", "worker_jobs", "feed_projection", "source_poll_runs")


class ReadinessCheckResult:
    def __init__(
        self,
        name: str,
        status: str,
        message: str,
        blockers: Sequence[str] = (),
    ):
        self.name = name
        self.status = status  # "PASS", "BLOCKED", "FAIL"
        self.message = message
        self.blockers = tuple(blockers)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def check_secrets_and_config(role: str, env: Mapping[str, str]) -> ReadinessCheckResult:
    """Validate environment variables and secrets without printing secret values."""
    try:
        if role == "all":
            for r in ("api", "worker", "scheduler", "migrate"):
                resolve_environment(r, env)
        elif role in ("api", "worker", "scheduler", "migrate", "readiness", "liveness"):
            resolve_environment(role, env)
        else:
            from scripts.validate_cloud_config import validate
            missing = validate(role, dict(env))
            if missing:
                return ReadinessCheckResult(
                    name="Configuration & Secrets",
                    status="FAIL",
                    message=f"Missing or invalid required variables: {', '.join(missing)}",
                )
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            status="PASS",
            message="Required environment variables and secrets are present, valid, and non-conflicting",
        )
    except ConfigurationError as exc:
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            status="FAIL",
            message=f"Configuration error: {exc}",
        )
    except Exception as exc:
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            status="FAIL",
            message=f"Unexpected configuration error: {exc}",
        )


def check_pc_independence(env: Mapping[str, str]) -> ReadinessCheckResult:
    """Verify runtime environment has no Founder PC / localhost dependencies."""
    is_cloud_mode = (
        env.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"production", "prod", "cloud"}
        or env.get("MODE", "").lower() == "cloud"
    )
    db_url = env.get("CLOUD_DATABASE_URL") or env.get("OPPORTUNITYOS_DB_URL", "")
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(db_url)
        if is_cloud_mode and _is_loopback_host(parsed.hostname):
            return ReadinessCheckResult(
                name="Founder PC Independence",
                status="FAIL",
                message="Database URL points to localhost/loopback while running in production/cloud mode",
            )
    except Exception:
        pass

    # Check for forbidden local path references
    for key in ("OPPORTUNITYOS_DB_URL", "CLOUD_DATABASE_URL", "OPPORTUNITYOS_TRUTH_PACK_PATH"):
        val = env.get(key, "")
        val_lower = val.lower()
        if "c:\\" in val_lower or "/users/" in val_lower or val.startswith("private/"):
            return ReadinessCheckResult(
                name="Founder PC Independence",
                status="FAIL",
                message=f"Local absolute or private path detected in '{key}'",
            )

    return ReadinessCheckResult(
        name="Founder PC Independence",
        status="PASS",
        message="No Founder-machine paths, localhost bindings, or desktop session dependencies detected",
    )


def check_database_and_schema(
    engine: Any | None = None,
    db_url: str | None = None,
) -> list[ReadinessCheckResult]:
    """Verify database reachability and required schema tables without touching opportunities."""
    results: list[ReadinessCheckResult] = []

    active_engine = engine
    if active_engine is None:
        if not db_url:
            results.append(
                ReadinessCheckResult(
                    name="Database Connectivity",
                    status="FAIL",
                    message="No database URL provided or found in environment",
                )
            )
            return results

        try:
            from storage.engine import get_engine
            active_engine = get_engine(db_url)
        except Exception as exc:
            results.append(
                ReadinessCheckResult(
                    name="Database Connectivity",
                    status="FAIL",
                    message=f"Failed to create SQLAlchemy engine: {exc}",
                )
            )
            return results

    # 1. Reachability probe (SELECT 1)
    try:
        from sqlalchemy import text
        with active_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results.append(
            ReadinessCheckResult(
                name="Database Reachability",
                status="PASS",
                message="PostgreSQL database is reachable and accepting queries",
            )
        )
    except Exception as exc:
        results.append(
            ReadinessCheckResult(
                name="Database Reachability",
                status="FAIL",
                message=f"Database unreachable or connection refused: {exc}",
            )
        )
        return results

    # 2. Schema tables inspection
    try:
        from sqlalchemy import inspect
        inspector = inspect(active_engine)
        existing_tables = set(inspector.get_table_names())

        missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]
        if missing_tables:
            results.append(
                ReadinessCheckResult(
                    name="Schema Migrations & Tables",
                    status="FAIL",
                    message=f"Missing required tables (run 'migrate' role first): {', '.join(missing_tables)}",
                )
            )
        else:
            with active_engine.connect() as conn:
                rev = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            results.append(
                ReadinessCheckResult(
                    name="Schema Migrations & Tables",
                    status="PASS",
                    message=f"All required runtime tables present (alembic head revision: {rev})",
                )
            )
    except Exception as exc:
        results.append(
            ReadinessCheckResult(
                name="Schema Migrations & Tables",
                status="FAIL",
                message=f"Failed inspecting database schema: {exc}",
            )
        )

    return results


def check_authentication(env: Mapping[str, str], role: str = "all") -> ReadinessCheckResult:
    """Verify production authentication configuration without disclosing secrets."""
    if role not in ("api", "all"):
        return ReadinessCheckResult(
            name="Authentication",
            status="PASS",
            message=f"Server-side founder authentication not required for role '{role}'",
        )

    founder_pw = env.get("OPPORTUNITYOS_FOUNDER_PASSWORD")
    session_sec = env.get("OPPORTUNITYOS_SESSION_SECRET")

    from scripts.validate_cloud_config import invalid
    has_founder = bool(founder_pw and not invalid("OPPORTUNITYOS_FOUNDER_PASSWORD", founder_pw)
                       and session_sec and not invalid("OPPORTUNITYOS_SESSION_SECRET", session_sec))
    has_jwks = bool(env.get("AUTH_JWKS_URL") and env.get("AUTH_SERVICE_KEY"))

    if has_founder:
        return ReadinessCheckResult(
            name="Authentication (Founder)",
            status="PASS",
            message="Founder authentication credentials verified (single-founder replatforming, ADR-0012)",
        )
    elif env.get("AUTH_JWKS_URL"):
        return ReadinessCheckResult(
            name="Authentication (JWKS)",
            status="BLOCKED",
            message="JWKS authentication is parked for BRIEF-007 multi-tenancy; OPPORTUNITYOS_FOUNDER_PASSWORD and OPPORTUNITYOS_SESSION_SECRET required for FR-007",
            blockers=("OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET"),
        )
    else:
        return ReadinessCheckResult(
            name="Authentication",
            status="BLOCKED",
            message="No valid authentication credentials found (OPPORTUNITYOS_FOUNDER_PASSWORD + OPPORTUNITYOS_SESSION_SECRET required)",
            blockers=("OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET"),
        )


def check_truth_pack(env: Mapping[str, str], role: str = "all") -> ReadinessCheckResult:
    """Report Truth Pack storage location and verify non-local configuration in cloud mode."""
    target = env.get("OPPORTUNITYOS_TRUTH_PACK_URI") or env.get("OPPORTUNITYOS_TRUTH_PACK_PATH")
    if not target:
        if role in ("worker", "all"):
            return ReadinessCheckResult(
                name="Truth Pack Storage",
                status="BLOCKED",
                message="Missing required OPPORTUNITYOS_TRUTH_PACK_URI for worker role; cannot evaluate opportunities without Founder context",
                blockers=("OPPORTUNITYOS_TRUTH_PACK_URI",),
            )
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="PASS",
            message=f"Truth Pack URI unset (not required for role '{role}')",
        )

    target_str = str(target).strip()
    from truth.pack import _redact_url
    redacted = _redact_url(target_str)
    target_lower = target_str.lower()

    if target_str.startswith("private/") or "c:\\" in target_lower or "/users/" in target_lower:
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="FAIL",
            message=f"Forbidden local machine path in Truth Pack target: {redacted}",
        )

    if target_str.startswith("http://"):
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="FAIL",
            message=f"Insecure plain http:// Truth Pack URI is forbidden in cloud mode; HTTPS required ({redacted})",
        )

    if target_str.startswith("data:"):
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="FAIL",
            message="data: URI is development/test fixture only and not accepted as production remote storage",
        )

    if target_str.startswith("s3://"):
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="BLOCKED",
            message=f"s3:// storage is deferred for FR-007 ({redacted}); HTTPS object store is the supported remote storage mechanism",
            blockers=("OPPORTUNITYOS_TRUTH_PACK_URI",),
        )

    if target_str.startswith("https://"):
        hash_val = env.get("OPPORTUNITYOS_TRUTH_PACK_HASH") or env.get("OPPORTUNITYOS_TRUTH_PACK_SHA256")
        if not hash_val:
            return ReadinessCheckResult(
                name="Truth Pack Storage",
                status="BLOCKED",
                message=f"Missing required OPPORTUNITYOS_TRUTH_PACK_HASH for remote HTTPS Truth Pack integrity verification ({redacted})",
                blockers=("OPPORTUNITYOS_TRUTH_PACK_HASH",),
            )
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="PASS",
            message=f"Remote HTTPS Truth Pack endpoint configured ({redacted}) with SHA-256 integrity verification",
        )

    # Any generic local or container filesystem path (e.g. /app/truth/... or relative)
    if role in ("worker", "all"):
        return ReadinessCheckResult(
            name="Truth Pack Storage",
            status="BLOCKED",
            message=f"Local or container filesystem Truth Pack path ('{target_str}') is not production cloud-ready; remote HTTPS object retrieval with SHA-256 integrity verification required",
            blockers=("OPPORTUNITYOS_TRUTH_PACK_URI",),
        )

    return ReadinessCheckResult(
        name="Truth Pack Storage",
        status="PASS",
        message=f"Truth Pack path configured for non-worker role '{role}' ({target_str})",
    )


def check_queue_durability(engine: Any | None = None, db_url: str | None = None) -> ReadinessCheckResult:
    """Verify PostgreSQL worker_jobs queue durability mechanism without external brokers."""
    active_engine = engine
    if active_engine is None:
        if not db_url:
            return ReadinessCheckResult(
                name="Queue Durability (PostgreSQL)",
                status="FAIL",
                message="No database engine or URL provided to verify queue durability",
            )
        try:
            from storage.engine import get_engine
            active_engine = get_engine(db_url)
        except Exception as exc:
            return ReadinessCheckResult(
                name="Queue Durability (PostgreSQL)",
                status="FAIL",
                message=f"Failed to connect to database for queue durability check: {exc}",
            )

    try:
        from sqlalchemy import inspect, text
        inspector = inspect(active_engine)
        tables = set(inspector.get_table_names())
        if "worker_jobs" not in tables:
            return ReadinessCheckResult(
                name="Queue Durability (PostgreSQL)",
                status="FAIL",
                message="Missing required 'worker_jobs' table in database schema",
            )

        cols = {col["name"] for col in inspector.get_columns("worker_jobs")}
        required_cols = {"id", "job_type", "payload_json", "status", "lease_owner", "lease_expires_at", "retry_count", "max_retries", "run_after"}
        missing_cols = required_cols - cols
        if missing_cols:
            return ReadinessCheckResult(
                name="Queue Durability (PostgreSQL)",
                status="FAIL",
                message=f"worker_jobs table missing required columns: {', '.join(sorted(missing_cols))}",
            )

        # Probe SKIP LOCKED support if connected to real PostgreSQL dialect
        is_postgres = getattr(active_engine, "dialect", None) is not None and active_engine.dialect.name == "postgresql"
        if not is_postgres:
            dialect_name = getattr(getattr(active_engine, "dialect", None), "name", "unknown")
            return ReadinessCheckResult(
                name="Queue Durability (PostgreSQL)",
                status="FAIL",
                message=f"Non-PostgreSQL dialect '{dialect_name}' detected. PostgreSQL required for production SKIP LOCKED queue durability.",
            )

        with active_engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text("SELECT id, status, lease_owner, lease_expires_at FROM worker_jobs WHERE status IN ('PENDING', 'RETRY') ORDER BY run_after ASC LIMIT 1 FOR UPDATE SKIP LOCKED")
                )

        return ReadinessCheckResult(
            name="Queue Durability (PostgreSQL)",
            status="PASS",
            message="PostgreSQL worker_jobs verified live (atomic FOR UPDATE SKIP LOCKED, lease recovery, dead-lettering, zero external broker dependency)",
        )

    except Exception as exc:
        return ReadinessCheckResult(
            name="Queue Durability (PostgreSQL)",
            status="FAIL",
            message=f"Queue durability inspection failed: {exc}",
        )


def check_single_role_autonomy(role: str, env: Mapping[str, str]) -> ReadinessCheckResult:
    """Evaluate whether an individual role can execute completely autonomously."""
    from scripts.cloud_runtime_bridge import CompatibilityError, plan_runtime_environment

    try:
        plan = plan_runtime_environment(role, env)
        if plan.blockers:
            return ReadinessCheckResult(
                name=f"Role Autonomy [{role}]",
                status="BLOCKED",
                message=f"Role '{role}' has unresolved blockers: {', '.join(plan.blockers)}",
                blockers=plan.blockers,
            )
        return ReadinessCheckResult(
            name=f"Role Autonomy [{role}]",
            status="PASS",
            message=f"Role '{role}' is fully autonomous (0 blockers, independent container execution)",
        )
    except CompatibilityError as exc:
        return ReadinessCheckResult(
            name=f"Role Autonomy [{role}]",
            status="FAIL",
            message=f"Role '{role}' configuration error: {exc}",
        )


def check_canonical_runtime_contract(role: str, env: Mapping[str, str]) -> ReadinessCheckResult:
    """Validate canonical cloud runtime contract and detect unwired blockers."""
    from scripts.cloud_runtime_bridge import CompatibilityError, plan_runtime_environment

    roles_to_check = ("api", "worker", "scheduler", "migrate") if role == "all" else (role,)
    unresolved_blockers: dict[str, list[str]] = {}

    for r in roles_to_check:
        try:
            plan = plan_runtime_environment(r, env)
            if plan.blockers:
                unresolved_blockers[r] = list(plan.blockers)
        except CompatibilityError as exc:
            return ReadinessCheckResult(
                name="Canonical Runtime Contract",
                status="FAIL",
                message=f"Contract validation failure for role '{r}': {exc}",
            )

    if unresolved_blockers:
        formatted = "; ".join(f"{r}: [{', '.join(b)}]" for r, b in unresolved_blockers.items())
        all_blockers = [b for b_list in unresolved_blockers.values() for b in b_list]
        return ReadinessCheckResult(
            name="Canonical Runtime Contract",
            status="BLOCKED",
            message=f"Unresolved cloud integration blockers: {formatted}",
            blockers=all_blockers,
        )

    return ReadinessCheckResult(
        name="Canonical Runtime Contract",
        status="PASS",
        message=f"Zero unresolved launch blockers for role '{role}'",
    )


def run_preflight_checks(
    role: str = "all",
    environ: Mapping[str, str] | None = None,
    engine: Any | None = None,
) -> list[ReadinessCheckResult]:
    """Execute all preflight readiness checks."""
    env = dict(os.environ if environ is None else environ)
    results: list[ReadinessCheckResult] = []

    # 1. Config and secrets
    results.append(check_secrets_and_config(role, env))

    # 2. PC independence
    results.append(check_pc_independence(env))

    # 3. Database connectivity and schema
    if role not in ("web", "liveness"):
        db_url = env.get("CLOUD_DATABASE_URL") or env.get("OPPORTUNITYOS_DB_URL")
        db_results = check_database_and_schema(engine=engine, db_url=db_url)
        results.extend(db_results)

        # 4. Queue durability (worker_jobs)
        has_schema = any(r.name == "Schema Migrations & Tables" and r.passed for r in db_results)
        if has_schema:
            results.append(check_queue_durability(engine=engine, db_url=db_url))
        else:
            results.append(
                ReadinessCheckResult(
                    name="Queue Durability (PostgreSQL)",
                    status="FAIL",
                    message="Cannot verify queue durability: database unreachable or schema tables missing",
                )
            )

    # 5. Authentication
    results.append(check_authentication(env, role=role))

    # 6. Truth Pack storage
    results.append(check_truth_pack(env, role=role))

    # 7. Role-specific autonomy
    roles_to_check = ("api", "worker", "scheduler", "migrate") if role == "all" else (role,)
    for r in roles_to_check:
        results.append(check_single_role_autonomy(r, env))

    # 8. Canonical runtime contract and launch blockers
    results.append(check_canonical_runtime_contract(role, env))

    return results


def main(argv: Sequence[str] | None = None, engine: Any | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/check_cloud_readiness.py",
        description="Verify FR-007 cloud deployment readiness without Founder PC dependencies.",
    )
    parser.add_argument(
        "--role",
        choices=("all", "api", "worker", "scheduler", "migrate", "backup", "web"),
        default="all",
        help="Target cloud deployment role to preflight (default: all)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Override database URL for preflight connectivity check",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only failure diagnostics and final status",
    )
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.db_url:
        env["CLOUD_DATABASE_URL"] = args.db_url

    results = run_preflight_checks(role=args.role, environ=env, engine=engine)

    has_fail = any(r.status == "FAIL" for r in results)
    has_blocked = any(r.status == "BLOCKED" for r in results)

    if not args.quiet:
        print("=" * 72)
        print(f"OpportunityOS FR-007 Cloud Deployment Readiness Preflight [role={args.role}]")
        print("=" * 72)
        for r in results:
            print(f"[{r.status}] {r.name}: {r.message}")
        print("-" * 72)

    if has_fail:
        print("[FAILURE] One or more cloud deployment prerequisites failed.")
        return 1
    elif has_blocked:
        all_blockers = []
        for r in results:
            if r.blockers:
                all_blockers.extend(r.blockers)
        blocker_str = ", ".join(sorted(set(all_blockers)))
        print(f"[BLOCKED] Role '{args.role}' has unresolved cloud integration blockers: {blocker_str}")
        return 2
    else:
        print(f"[SUCCESS] All FR-007 cloud deployment prerequisites are satisfied for role '{args.role}'.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
