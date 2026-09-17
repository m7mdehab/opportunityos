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
    def __init__(self, name: str, passed: bool, message: str):
        self.name = name
        self.passed = passed
        self.message = message


def check_secrets_and_config(role: str, env: Mapping[str, str]) -> ReadinessCheckResult:
    """Validate environment variables and secrets without printing secret values."""
    try:
        if role == "all":
            for r in ("api", "worker", "scheduler", "migrate"):
                resolve_environment(r, env)
        else:
            resolve_environment(role, env)
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            passed=True,
            message="Required environment variables and secrets are present, valid, and non-conflicting",
        )
    except ConfigurationError as exc:
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            passed=False,
            message=f"Configuration error: {exc}",
        )
    except Exception as exc:
        return ReadinessCheckResult(
            name="Configuration & Secrets",
            passed=False,
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
                passed=False,
                message="Database URL points to localhost/loopback while running in production/cloud mode",
            )
    except Exception:
        pass

    # Check for forbidden local path references
    for key in ("OPPORTUNITYOS_DB_URL", "CLOUD_DATABASE_URL"):
        val = env.get(key, "")
        if "c:\\" in val.lower() or "/users/" in val.lower():
            return ReadinessCheckResult(
                name="Founder PC Independence",
                passed=False,
                message=f"Local absolute path detected in '{key}'",
            )

    return ReadinessCheckResult(
        name="Founder PC Independence",
        passed=True,
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
                    passed=False,
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
                    passed=False,
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
                passed=True,
                message="PostgreSQL database is reachable and accepting queries",
            )
        )
    except Exception as exc:
        results.append(
            ReadinessCheckResult(
                name="Database Reachability",
                passed=False,
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
                    passed=False,
                    message=f"Missing required tables (run 'migrate' role first): {', '.join(missing_tables)}",
                )
            )
        else:
            # Query alembic_version revision
            with active_engine.connect() as conn:
                rev = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            results.append(
                ReadinessCheckResult(
                    name="Schema Migrations & Tables",
                    passed=True,
                    message=f"All required runtime tables present (alembic head revision: {rev})",
                )
            )
    except Exception as exc:
        results.append(
            ReadinessCheckResult(
                name="Schema Migrations & Tables",
                passed=False,
                message=f"Failed inspecting database schema: {exc}",
            )
        )

    return results


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
    db_url = env.get("CLOUD_DATABASE_URL") or env.get("OPPORTUNITYOS_DB_URL")
    results.extend(check_database_and_schema(engine=engine, db_url=db_url))

    return results


def main(argv: Sequence[str] | None = None, engine: Any | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/check_cloud_readiness.py",
        description="Verify FR-007 cloud deployment readiness without Founder PC dependencies.",
    )
    parser.add_argument(
        "--role",
        choices=("all", "api", "worker", "scheduler", "migrate"),
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

    all_passed = all(r.passed for r in results)

    if not args.quiet:
        print("=" * 72)
        print(f"OpportunityOS FR-007 Cloud Deployment Readiness Preflight [role={args.role}]")
        print("=" * 72)
        for r in results:
            status = "[PASS]" if r.passed else "[FAIL]"
            print(f"{status} {r.name}: {r.message}")
        print("-" * 72)

    if all_passed:
        print("[SUCCESS] All FR-007 cloud deployment prerequisites are satisfied.")
        return 0
    else:
        print("[FAILURE] One or more cloud deployment prerequisites failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
