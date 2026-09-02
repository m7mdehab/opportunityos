"""``python scripts/alpha.py up|down|status|logs`` -- the one-command local runner.

``up`` brings up, in order, waiting for each to be healthy before starting
the next: PostgreSQL (an already-running local server if one is listening on
127.0.0.1:5432, else the portable cluster FR-003 established under
``%LOCALAPPDATA%\\opos-pg\\``), ``alembic upgrade head``, the worker with
``--schedule`` (see ``worker.scheduler.PollScheduler``), the API on
``:8000``, and the web app on ``:3000``, then opens
``http://localhost:3000`` in the default browser. ``down`` stops everything
this script started, cleanly, and never stops a PostgreSQL server it did not
start. ``status`` reports each process's up/down state plus the last poll
per source (from ``source_poll_runs``). ``logs`` tails what it started.

Secrets (``OPPORTUNITYOS_FOUNDER_PASSWORD``, ``OPPORTUNITYOS_SESSION_SECRET``,
``OPPORTUNITYOS_DB_URL``) are read from ``private/alpha.env`` (never
committed; template at ``docs/templates/alpha.env.template``) -- never from
this module's own source. This module itself must never read, write, or
list anything under ``private/``; the default ``--env-file`` value below is
just a ``Path`` object (no filesystem access happens merely by importing
this module or constructing that default) -- filesystem access only happens
when ``load_alpha_env`` actually runs, which callers (including tests) can
redirect with ``--env-file``.

PID/log/state tracking lives under ``out/alpha_run/`` rather than
``private/``: ``out/`` is already excluded in full by the repository's
``.gitignore`` ("Third-party reconnaissance payloads and derived corpus"),
so reusing it avoids ever needing a new ``.gitignore`` entry -- and this
deliverable's file set does not include ``.gitignore``.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"

DEFAULT_ENV_FILE = REPO_ROOT / "private" / "alpha.env"
ENV_TEMPLATE_PATH = REPO_ROOT / "docs" / "templates" / "alpha.env.template"
DEFAULT_RUN_DIR = REPO_ROOT / "out" / "alpha_run"

REQUIRED_ENV_KEYS = (
    "OPPORTUNITYOS_FOUNDER_PASSWORD",
    "OPPORTUNITYOS_SESSION_SECRET",
    "OPPORTUNITYOS_DB_URL",
)

API_HOST = "127.0.0.1"
API_PORT = 8000
WEB_HOST = "127.0.0.1"
WEB_PORT = 3000
PG_HOST = "127.0.0.1"
PG_PORT = 5432

_PROCESS_LABELS = ("worker", "api", "web")


class AlphaError(RuntimeError):
    """Any ``up``/``down``/``status`` failure, with a founder-readable message."""


# ---------------------------------------------------------------------------
# private/alpha.env
# ---------------------------------------------------------------------------


def load_alpha_env(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from ``path``. Raises ``AlphaError`` with a
    clear, actionable message if the file is missing or incomplete.
    """
    if not path.exists():
        raise AlphaError(
            f"{path} not found. Copy {ENV_TEMPLATE_PATH} to {path} and fill in real values "
            "(private/ is gitignored, so this file is never committed)."
        )
    values: dict[str, str] = {}
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AlphaError(f"{path}:{lineno}: expected KEY=VALUE, got: {raw_line!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    missing = [key for key in REQUIRED_ENV_KEYS if not values.get(key)]
    if missing:
        raise AlphaError(
            f"{path} is missing required key(s): {', '.join(missing)}. See {ENV_TEMPLATE_PATH}."
        )
    return values


# ---------------------------------------------------------------------------
# process / port helpers
# ---------------------------------------------------------------------------


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout_seconds: float, description: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return
        time.sleep(0.5)
    raise AlphaError(
        f"Timed out after {timeout_seconds:.0f}s waiting for {description} to listen on {host}:{port}."
    )


def _wait_process_alive(proc: "subprocess.Popen", grace_seconds: float, description: str, log_path: Path) -> None:
    """Bounded smoke check: fail fast (with the log path) if the process died immediately."""
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AlphaError(
                f"{description} exited immediately (exit code {proc.returncode}). See {log_path} for details."
            )
        time.sleep(0.3)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill_pid_tree(pid: int) -> None:
    """Kill ``pid`` and its children -- npm/uvicorn spawn child processes that
    would otherwise be left holding ports 8000/3000 after ``down``.
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return
    import signal as _signal

    try:
        os.kill(pid, _signal.SIGTERM)
    except OSError:
        pass


def _spawn(cmd: list[str], cwd: Path, env: dict, log_path: Path) -> "subprocess.Popen":
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab")
    try:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise AlphaError(f"Failed to start `{' '.join(cmd)}` in {cwd}: {exc}") from exc
    finally:
        log_file.close()
    return proc


# ---------------------------------------------------------------------------
# state file (out/alpha_run/state.json)
# ---------------------------------------------------------------------------


def _state_path(run_dir: Path) -> Path:
    return run_dir / "state.json"


def _load_state(run_dir: Path) -> dict:
    path = _state_path(run_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(run_dir: Path, state: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _state_path(run_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clear_state(run_dir: Path) -> None:
    path = _state_path(run_dir)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# PostgreSQL bring-up / stop
# ---------------------------------------------------------------------------


def _ensure_postgres(run_dir: Path) -> dict:
    """Detect an already-listening PostgreSQL first; only start the portable
    cluster if nothing is listening on 127.0.0.1:5432. Returns a dict
    recording whether alpha.py itself started it (and how), so ``down``
    never stops a server it did not start.
    """
    if _port_open(PG_HOST, PG_PORT, timeout=1.0):
        print(f"PostgreSQL: already listening on {PG_HOST}:{PG_PORT} (not started by alpha.py).")
        return {"started_by_alpha": False}

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise AlphaError(
            f"PostgreSQL is not listening on {PG_HOST}:{PG_PORT} and %LOCALAPPDATA% is not set, so "
            "the portable cluster cannot be located. Start a PostgreSQL server on that host/port "
            "yourself, or set up the portable cluster per briefs/BRIEF-FR-003.md section 6."
        )
    base = Path(local_appdata) / "opos-pg"
    pg_ctl_name = "pg_ctl.exe" if os.name == "nt" else "pg_ctl"
    pg_ctl = base / "pgsql" / "bin" / pg_ctl_name
    data_dir = base / "data"
    if not pg_ctl.exists() or not data_dir.exists():
        raise AlphaError(
            f"PostgreSQL is not listening on {PG_HOST}:{PG_PORT} and no portable cluster was found "
            f"at {base} (expected {pg_ctl} and {data_dir}). Set up the portable cluster per "
            "briefs/BRIEF-FR-003.md section 6, or start your own PostgreSQL server on that host/port."
        )

    log_path = run_dir / "logs" / "postgres.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"PostgreSQL: not listening; starting the portable cluster at {data_dir} ...")
    result = subprocess.run(
        [
            str(pg_ctl),
            "start",
            "-D",
            str(data_dir),
            "-w",
            "-t",
            "30",
            "-o",
            f"-p {PG_PORT}",
            "-l",
            str(log_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AlphaError(
            "pg_ctl failed to start the portable PostgreSQL cluster at "
            f"{data_dir} (exit code {result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
            f"See also {log_path}."
        )
    if not _port_open(PG_HOST, PG_PORT, timeout=5.0):
        raise AlphaError(
            f"pg_ctl reported success but {PG_HOST}:{PG_PORT} is still not accepting connections. "
            f"See {log_path}."
        )
    print(f"PostgreSQL: started (data dir {data_dir}).")
    return {"started_by_alpha": True, "pg_ctl": str(pg_ctl), "data_dir": str(data_dir)}


def _stop_postgres(pg_info: dict) -> str:
    if not pg_info or not pg_info.get("started_by_alpha"):
        return "PostgreSQL: left running (alpha.py did not start it)."
    pg_ctl = pg_info.get("pg_ctl")
    data_dir = pg_info.get("data_dir")
    if not pg_ctl or not data_dir:
        return "PostgreSQL: alpha.py started it but the state file is missing pg_ctl/data_dir; stop it manually."
    result = subprocess.run(
        [pg_ctl, "stop", "-D", data_dir, "-m", "fast", "-w", "-t", "30"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return (
            f"PostgreSQL: `pg_ctl stop` failed (exit code {result.returncode}): "
            f"{result.stdout}\n{result.stderr}"
        )
    return "PostgreSQL: stopped (portable cluster started by alpha.py)."


def _run_alembic_upgrade(env: dict) -> None:
    print("Migrations: running `alembic upgrade head` ...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AlphaError(
            f"`alembic upgrade head` failed (exit code {result.returncode}).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    print("Migrations: up to date.")


def _stop_processes(processes: dict) -> list[str]:
    messages = []
    for label, info in processes.items():
        pid = info.get("pid")
        if pid is None:
            continue
        if _pid_alive(pid):
            _kill_pid_tree(pid)
            messages.append(f"{label}: stopped (was pid {pid}).")
        else:
            messages.append(f"{label}: already stopped (pid {pid} not running).")
    return messages


# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------


def cmd_up(env_file: Path, run_dir: Path) -> int:
    state = _load_state(run_dir)
    existing_processes = state.get("processes", {})
    if existing_processes and any(_pid_alive(info["pid"]) for info in existing_processes.values()):
        print(
            "alpha: a previous `up` session appears to still be running (per state file). "
            "Run `python scripts/alpha.py status` for details, or `python scripts/alpha.py down` "
            "first if you want to restart."
        )
        return 0

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    processes: dict[str, dict] = {}
    pg_info: dict = {}

    try:
        alpha_env_values = load_alpha_env(env_file)

        pg_info = _ensure_postgres(run_dir)

        env = os.environ.copy()
        env.update(alpha_env_values)

        _run_alembic_upgrade(env)

        worker_log = run_dir / "logs" / "worker.log"
        worker_proc = _spawn([sys.executable, "-m", "worker", "--schedule"], REPO_ROOT, env, worker_log)
        processes["worker"] = {"pid": worker_proc.pid, "log": str(worker_log)}
        _wait_process_alive(worker_proc, 3.0, "worker (--schedule)", worker_log)
        print(f"Worker: started (pid {worker_proc.pid}), logging to {worker_log}.")

        api_log = run_dir / "logs" / "api.log"
        api_proc = _spawn(
            [sys.executable, "-m", "uvicorn", "api.app:app", "--host", API_HOST, "--port", str(API_PORT)],
            REPO_ROOT,
            env,
            api_log,
        )
        processes["api"] = {"pid": api_proc.pid, "log": str(api_log)}
        _wait_process_alive(api_proc, 2.0, "API server", api_log)
        _wait_for_port(API_HOST, API_PORT, 30.0, "the API server")
        print(f"API: listening on {API_HOST}:{API_PORT} (pid {api_proc.pid}), logging to {api_log}.")

        if not (WEB_DIR / "node_modules").exists():
            raise AlphaError(
                f"{WEB_DIR / 'node_modules'} is missing. Run `npm install` in {WEB_DIR} once, then "
                "re-run `python scripts/alpha.py up`."
            )

        # alpha.py must run the web app against the real API, never the MSW
        # mock -- drop any inherited NEXT_PUBLIC_USE_MOCK_API=1 rather than
        # trust the founder's ambient shell not to have it set from other work.
        web_env = os.environ.copy()
        web_env.pop("NEXT_PUBLIC_USE_MOCK_API", None)
        web_log = run_dir / "logs" / "web.log"
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        web_proc = _spawn([npm_cmd, "run", "dev"], WEB_DIR, web_env, web_log)
        processes["web"] = {"pid": web_proc.pid, "log": str(web_log)}
        _wait_process_alive(web_proc, 2.0, "web (npm run dev)", web_log)
        _wait_for_port(WEB_HOST, WEB_PORT, 60.0, "the web dev server")
        print(f"Web: listening on {WEB_HOST}:{WEB_PORT} (pid {web_proc.pid}), logging to {web_log}.")

        state = {
            "processes": processes,
            "postgres": pg_info,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(run_dir, state)

        url = f"http://localhost:{WEB_PORT}"
        print(f"Opening {url} ...")
        try:
            webbrowser.open(url)
        except Exception:
            pass

        print("alpha: up.")
        return 0
    except AlphaError as exc:
        print(f"alpha up: FAILED: {exc}", file=sys.stderr)
        if processes or pg_info:
            print("alpha up: rolling back anything this run started ...", file=sys.stderr)
            for message in _stop_processes(processes):
                print(message, file=sys.stderr)
            if pg_info:
                print(_stop_postgres(pg_info), file=sys.stderr)
        _clear_state(run_dir)
        return 1


# ---------------------------------------------------------------------------
# down
# ---------------------------------------------------------------------------


def cmd_down(run_dir: Path) -> int:
    state = _load_state(run_dir)
    if not state:
        print(f"alpha: no session recorded under {run_dir} (nothing to stop).")
        return 0

    for message in _stop_processes(state.get("processes", {})):
        print(message)

    print(_stop_postgres(state.get("postgres", {})))

    _clear_state(run_dir)
    print("alpha: down.")
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(env_file: Path, run_dir: Path) -> int:
    state = _load_state(run_dir)
    processes = state.get("processes", {})

    print("alpha status")
    print("------------")
    for label in _PROCESS_LABELS:
        info = processes.get(label)
        if info and _pid_alive(info["pid"]):
            print(f"  {label}: up (pid {info['pid']})")
        else:
            print(f"  {label}: down")

    pg_info = state.get("postgres", {})
    if _port_open(PG_HOST, PG_PORT, timeout=1.0):
        ownership = "started by alpha.py" if pg_info.get("started_by_alpha") else "external/pre-existing"
        print(f"  postgres: listening on {PG_HOST}:{PG_PORT} ({ownership})")
    else:
        print(f"  postgres: not listening on {PG_HOST}:{PG_PORT}")

    print()
    print("last poll per source:")
    try:
        alpha_env_values = load_alpha_env(env_file)
    except AlphaError as exc:
        print(f"  (unavailable: {exc})")
        return 0

    try:
        from storage.engine import get_engine, get_session_factory
        from storage.models import SourcePollRunRecord

        engine = get_engine(alpha_env_values["OPPORTUNITYOS_DB_URL"])
        session_factory = get_session_factory(engine)
        session = session_factory()
        try:
            rows = (
                session.query(SourcePollRunRecord)
                .order_by(SourcePollRunRecord.source_id, SourcePollRunRecord.started_at.desc())
                .all()
            )
            latest_by_source: dict[str, SourcePollRunRecord] = {}
            for row in rows:
                latest_by_source.setdefault(row.source_id, row)
            if not latest_by_source:
                print("  (no polls recorded yet)")
            for source_id, row in sorted(latest_by_source.items()):
                print(f"  {source_id}: {row.status} at {row.started_at.isoformat()} (raw_ingested={row.raw_ingested})")
        finally:
            session.close()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - status must degrade gracefully, never crash, on any DB problem
        print(f"  (unavailable: could not query the database: {exc})")

    return 0


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


def cmd_logs(run_dir: Path, tail_lines: int = 40) -> int:
    state = _load_state(run_dir)
    processes = state.get("processes", {})
    if not processes:
        print(f"alpha: no session recorded under {run_dir}; nothing to show. Run `python scripts/alpha.py up` first.")
        return 0

    for label, info in processes.items():
        log_path = Path(info.get("log", ""))
        print(f"===== {label} ({log_path}) =====")
        if not log_path.exists():
            print("  (no log file)")
            continue
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-tail_lines:]:
            print(f"  {line}")
        print()

    pg_info = state.get("postgres", {})
    if pg_info.get("started_by_alpha"):
        pg_log = run_dir / "logs" / "postgres.log"
        print(f"===== postgres ({pg_log}) =====")
        if pg_log.exists():
            for line in pg_log.read_text(encoding="utf-8", errors="replace").splitlines()[-tail_lines:]:
                print(f"  {line}")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/alpha.py",
        description="One-command local runner for the OpportunityOS founder alpha.",
    )
    parser.add_argument("command", choices=["up", "down", "status", "logs"])
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to alpha.env (default: {DEFAULT_ENV_FILE}). Tests must override this so private/ is never read.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=DEFAULT_RUN_DIR,
        help=f"Directory for PID/log/state tracking (default: {DEFAULT_RUN_DIR}).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.command == "up":
        return cmd_up(args.env_file, args.run_dir)
    if args.command == "down":
        return cmd_down(args.run_dir)
    if args.command == "status":
        return cmd_status(args.env_file, args.run_dir)
    if args.command == "logs":
        return cmd_logs(args.run_dir)
    return 2  # unreachable: argparse's `choices` already rejects anything else


if __name__ == "__main__":
    raise SystemExit(main())
