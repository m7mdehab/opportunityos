#!/usr/bin/env python3
"""OpportunityOS OCI Container Role Entrypoint.

Dispatches explicit, isolated runtime roles for independently deployable
cloud containers:
  - api: Uvicorn HTTP server binding 0.0.0.0 (no scheduler, no background worker)
  - worker: Background queue processor (no API, no scheduler)
  - scheduler: Periodic poll scheduler (no API, no worker queue processing)
  - migrate: One-shot Alembic migration runner (no long-running daemon)
  - readiness: Lightweight DB connectivity/migration health probe (no corpus scan)
  - liveness: Lightweight process liveness probe

Fail-closed: Unrecognized roles, missing required secrets/variables, or
cross-role violations immediately exit non-zero.
"""
from __future__ import annotations

import ipaddress
import os
import pathlib
import re
import signal
import sys
import threading
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

# Ensure repository root is on sys.path when invoked directly as a script
REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

ROLES = ("api", "worker", "scheduler", "migrate", "readiness", "liveness")

# Internal command string for scheduler loop execution
SCHEDULER_INTERNAL_COMMAND = "_scheduler_loop"

# Template / placeholder detection pattern
PLACEHOLDER_PATTERN = re.compile(r"(?i)(replace[_ -]?me|placeholder|your[_ -]|<[^>]+>|\$\{|example\.)")

# Permitted database URL schemes for cloud/production PostgreSQL
VALID_DB_SCHEMES = {"postgresql", "postgresql+psycopg2"}


class ContainerRuntimeError(RuntimeError):
    """Base exception for container runtime errors."""


class InvalidRoleError(ContainerRuntimeError):
    """Raised when an invalid or unsupported role is specified."""


class ConfigurationError(ContainerRuntimeError):
    """Raised when required environment configuration is missing or invalid."""


class RoleSeparationError(ContainerRuntimeError):
    """Raised when role boundaries or separation invariants are violated."""


def _check_malformed_value(name: str, value: str) -> str | None:
    """Return diagnostic error string if value is malformed, otherwise None.

    Never includes or echoes secret values in the diagnostic message.
    """
    if not value or not value.strip():
        return f"Variable '{name}' is empty or whitespace-only"
    if value != value.strip():
        return f"Variable '{name}' contains leading or trailing whitespace"
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return f"Variable '{name}' contains illegal control characters"
    if PLACEHOLDER_PATTERN.search(value):
        return f"Variable '{name}' contains placeholder or unconfigured template text"
    return None


def _is_loopback_host(host: str | None) -> bool:
    """Return True if host resolves to localhost/loopback."""
    if not host:
        return True
    host_lower = host.lower()
    if host_lower in {"localhost", "host.docker.internal"} or host_lower.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_environment(role: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Validate and adapt runtime environment for the requested role.

    Fails closed if required variables are missing or malformed. Safely maps
    CLOUD_DATABASE_URL to OPPORTUNITYOS_DB_URL if set, while rejecting conflicting
    definitions. Never prints secret values.
    """
    env = dict(os.environ if environ is None else environ)

    # 1. Database URL aliasing and conflict detection
    cloud_db = env.get("CLOUD_DATABASE_URL")
    legacy_db = env.get("OPPORTUNITYOS_DB_URL")

    if cloud_db and not legacy_db:
        env["OPPORTUNITYOS_DB_URL"] = cloud_db
    elif legacy_db and not cloud_db:
        env["CLOUD_DATABASE_URL"] = legacy_db
    elif cloud_db and legacy_db and cloud_db != legacy_db:
        raise ConfigurationError("Conflicting variables: CLOUD_DATABASE_URL and OPPORTUNITYOS_DB_URL differ")

    # 2. Check missing vs malformed database URL for DB-dependent roles
    if role in ("api", "worker", "scheduler", "migrate", "readiness"):
        active_db = env.get("OPPORTUNITYOS_DB_URL")
        if not active_db:
            raise ConfigurationError(
                f"Missing required database configuration for role '{role}': "
                "OPPORTUNITYOS_DB_URL or CLOUD_DATABASE_URL must be set."
            )
        malformed = _check_malformed_value("DATABASE_URL", active_db)
        if malformed:
            raise ConfigurationError(f"Malformed configuration: {malformed}")

        try:
            parsed = urlsplit(active_db)
            if parsed.scheme not in VALID_DB_SCHEMES or not parsed.hostname:
                raise ConfigurationError(
                    f"Malformed database configuration: scheme must be one of {VALID_DB_SCHEMES}, got '{parsed.scheme}'"
                )
        except ValueError as exc:
            raise ConfigurationError(f"Malformed database URL: unparseable endpoint ({exc})") from exc

        # Production loopback rejection
        is_cloud_mode = (
            env.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"production", "prod", "cloud"}
            or env.get("MODE", "").lower() == "cloud"
        )
        if is_cloud_mode and _is_loopback_host(parsed.hostname):
            raise ConfigurationError(
                "Invalid cloud database endpoint: loopback host rejected in production/cloud mode"
            )

    # 3. Authoritative role-specific credential/config validation.
    #
    # Do not duplicate the auth contract here. The cloud runtime accepts the
    # W15A hash-only Founder credential and explicitly forbids plaintext
    # OPPORTUNITYOS_FOUNDER_PASSWORD, while local/dev compatibility still
    # accepts the plaintext credential. The bridge/validator below owns that
    # mode-sensitive decision and redacts supplied values from diagnostics.
    try:
        from scripts.cloud_runtime_bridge import (
            CompatibilityError,
            plan_runtime_environment,
        )
    except ImportError:
        from cloud_runtime_bridge import (  # type: ignore[no-redef]
            CompatibilityError,
            plan_runtime_environment,
        )

    try:
        bridge_plan = plan_runtime_environment(role, env)
        cloud_runtime = (
            env.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"production", "prod", "cloud"}
            or env.get("MODE", "").lower() == "cloud"
        )
        if cloud_runtime and bridge_plan.blockers:
            raise CompatibilityError(
                "Unwired cloud runtime dependencies: " + ", ".join(bridge_plan.blockers)
            )
        env.update(bridge_plan.aliases)
    except CompatibilityError as exc:
        raise ConfigurationError(f"Cloud runtime validation failed: {exc}") from exc

    return env


def build_role_command(
    role: str,
    extra_args: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Construct deterministic execution command for a given role.

    Enforces cloud network binding (0.0.0.0) and role separation invariants.
    """
    if role not in ROLES and role != SCHEDULER_INTERNAL_COMMAND:
        raise InvalidRoleError(
            f"Invalid role '{role}'. Supported roles: {', '.join(ROLES)}"
        )

    env = resolve_environment(role, environ)
    args = list(extra_args) if extra_args else []

    if role == "api":
        host = env.get("HOST") or env.get("OPPORTUNITYOS_API_HOST") or "0.0.0.0"
        port = env.get("PORT") or env.get("OPPORTUNITYOS_API_PORT") or "8000"
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "api.app:app",
            "--host",
            host,
            "--port",
            str(port),
            "--proxy-headers",
            "--forwarded-allow-ips=*",
        ]

    if role == "worker":
        # Strict role separation: dedicated worker must not run scheduler thread
        if "--schedule" in args:
            raise RoleSeparationError(
                "Role separation violation: '--schedule' cannot be used with the dedicated worker role. "
                "Use the 'scheduler' role instead."
            )
        return [sys.executable, "-m", "worker", *args]

    if role == "scheduler":
        return [sys.executable, __file__, SCHEDULER_INTERNAL_COMMAND]

    if role == "migrate":
        return [sys.executable, "-m", "alembic", "upgrade", "head"]

    if role in ("readiness", "liveness"):
        return [sys.executable, __file__, f"_probe_{role}"]

    if role == SCHEDULER_INTERNAL_COMMAND:
        return [sys.executable, __file__, SCHEDULER_INTERNAL_COMMAND]

    raise InvalidRoleError(f"Unsupported role: {role}")


def run_scheduler(
    session_factory: Callable[[], Any] | None = None,
    tick_seconds: float = 30.0,
    stop_event: threading.Event | None = None,
) -> int:
    """Run dedicated PollScheduler loop with graceful SIGTERM/SIGINT handling."""
    from storage.engine import get_engine, get_production_db_url, get_session_factory
    from worker.scheduler import PollScheduler

    event = stop_event if stop_event is not None else threading.Event()

    def _sig_handler(_signum: int, _frame: Any) -> None:
        event.set()

    # Install signal handlers if in main thread
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass

    if session_factory is None:
        db_url = get_production_db_url()
        engine = get_engine(db_url)
        factory = get_session_factory(engine)
    else:
        factory = session_factory

    scheduler = PollScheduler(factory, stop_event=event, tick_interval_seconds=tick_seconds)
    scheduler.run_forever()
    return 0


def run_readiness(session_factory: Callable[[], Any] | None = None) -> int:
    """Lightweight readiness probe for container orchestrators.

    Proves database connectivity and migration state without:
    - loading all opportunities
    - warming up caches
    - traversing truth pack or 33k rows
    - rebuilding feed projections
    """
    try:
        if session_factory is None:
            from storage.engine import get_engine, get_production_db_url, get_session_factory
            db_url = get_production_db_url()
            engine = get_engine(db_url)
            factory = get_session_factory(engine)
        else:
            factory = session_factory

        session = factory()
        try:
            from sqlalchemy import text

            # 1. Probe database connectivity
            session.execute(text("SELECT 1"))

            # 2. Probe migration presence
            session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            sys.stdout.write("readiness probe: ok (db reachable, migrations verified)\n")
            return 0
        finally:
            session.close()
    except Exception as exc:
        sys.stderr.write(f"readiness probe: failed ({exc})\n")
        return 1


def run_liveness() -> int:
    """Lightweight liveness probe."""
    sys.stdout.write("liveness probe: ok\n")
    return 0


def main(argv: Sequence[str] | None = None, exec_fn: Callable[..., Any] | None = None) -> int:
    """Main container entrypoint CLI."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        sys.stderr.write(
            "Error: No role specified.\n"
            f"Usage: python {sys.argv[0]} <role> [args...]\n"
            f"Supported roles: {', '.join(ROLES)}\n"
        )
        return 2

    if args[0] in ("-h", "--help"):
        sys.stdout.write(
            f"Usage: python {sys.argv[0]} [--dry-run] <role> [args...]\n"
            f"Supported roles: {', '.join(ROLES)}\n"
        )
        return 0

    dry_run = False
    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")
        if not args:
            sys.stderr.write("Error: No role specified after --dry-run.\n")
            return 2

    role = args[0]
    extra_args = args[1:]

    # Internal subcommands
    if role == SCHEDULER_INTERNAL_COMMAND:
        resolve_environment("scheduler")
        return run_scheduler()

    if role == "_probe_readiness":
        return run_readiness()

    if role == "_probe_liveness":
        return run_liveness()

    # Public roles
    if role not in ROLES:
        sys.stderr.write(
            f"Error: Invalid role '{role}'.\n"
            f"Supported roles: {', '.join(ROLES)}\n"
        )
        return 1

    try:
        env = resolve_environment(role)
        os.environ.update(env)

        if dry_run:
            import json
            cmd = build_role_command(role, extra_args, env)
            sys.stdout.write(f"DRY_RUN_COMMAND: {json.dumps(cmd)}\n")
            return 0

        if role == "readiness":
            return run_readiness()

        if role == "liveness":
            return run_liveness()

        if role == "scheduler":
            return run_scheduler()

        cmd = build_role_command(role, extra_args, env)

        if exec_fn is not None:
            return exec_fn(cmd)

        if hasattr(os, "execvp"):
            os.execvp(cmd[0], cmd)
        else:
            import subprocess
            return subprocess.run(cmd, check=False).returncode

    except ContainerRuntimeError as exc:
        sys.stderr.write(f"Container runtime error: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Unexpected entrypoint failure: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
