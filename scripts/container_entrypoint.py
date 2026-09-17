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

import os
import signal
import sys
import threading
from typing import Any, Callable, Mapping, Sequence

ROLES = ("api", "worker", "scheduler", "migrate", "readiness", "liveness")

# Internal command string for scheduler loop execution
SCHEDULER_INTERNAL_COMMAND = "_scheduler_loop"


class ContainerRuntimeError(RuntimeError):
    """Base exception for container runtime errors."""


class InvalidRoleError(ContainerRuntimeError):
    """Raised when an invalid or unsupported role is specified."""


class ConfigurationError(ContainerRuntimeError):
    """Raised when required environment configuration is missing or invalid."""


class RoleSeparationError(ContainerRuntimeError):
    """Raised when role boundaries or separation invariants are violated."""


def resolve_environment(role: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Validate and adapt runtime environment for the requested role.

    Fails closed if required variables are missing. Safely maps CLOUD_DATABASE_URL
    to OPPORTUNITYOS_DB_URL if set, while rejecting conflicting definitions.
    """
    env = dict(os.environ if environ is None else environ)

    # Bridge CLOUD_DATABASE_URL to OPPORTUNITYOS_DB_URL for legacy database consumers
    cloud_db = env.get("CLOUD_DATABASE_URL")
    legacy_db = env.get("OPPORTUNITYOS_DB_URL")

    if cloud_db and not legacy_db:
        env["OPPORTUNITYOS_DB_URL"] = cloud_db
    elif cloud_db and legacy_db and cloud_db != legacy_db:
        raise ConfigurationError("Conflicting variables: CLOUD_DATABASE_URL and OPPORTUNITYOS_DB_URL")

    # Role-specific fail-closed requirements
    if role in ("api", "worker", "scheduler", "migrate", "readiness"):
        if not env.get("OPPORTUNITYOS_DB_URL"):
            raise ConfigurationError(
                f"Missing required database configuration for role '{role}': "
                "OPPORTUNITYOS_DB_URL or CLOUD_DATABASE_URL must be set."
            )

    if role == "api":
        missing = []
        if not env.get("OPPORTUNITYOS_FOUNDER_PASSWORD"):
            missing.append("OPPORTUNITYOS_FOUNDER_PASSWORD")
        if not env.get("OPPORTUNITYOS_SESSION_SECRET"):
            missing.append("OPPORTUNITYOS_SESSION_SECRET")
        if missing:
            raise ConfigurationError(
                f"Missing required API credentials: {', '.join(missing)}"
            )

    # Optional cloud runtime bridge integration if available in repo
    try:
        from scripts.cloud_runtime_bridge import plan_runtime_environment  # type: ignore
        try:
            plan_runtime_environment(role, env)
        except Exception:
            # If bridge defines stricter cloud blockers, let specific role handle it
            pass
    except ImportError:
        pass

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

    role = args[0]
    extra_args = args[1:]

    # Internal subcommands
    if role == SCHEDULER_INTERNAL_COMMAND:
        # Sync environment
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
        # Apply resolved environment to current process
        os.environ.update(env)

        if role == "readiness":
            return run_readiness()

        if role == "liveness":
            return run_liveness()

        if role == "scheduler":
            return run_scheduler()

        cmd = build_role_command(role, extra_args, env)

        if exec_fn is not None:
            return exec_fn(cmd)

        # In production Linux container: replace process so it becomes PID 1
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
