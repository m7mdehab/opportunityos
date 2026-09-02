"""``python scripts/alpha.py up|down|status|logs`` -- the one-command local runner.

``up`` brings up, in order, waiting for each to be healthy before starting
the next: PostgreSQL (an already-running local server if one is listening on
127.0.0.1:5432, else the portable cluster FR-003 established under
``%LOCALAPPDATA%\\opos-pg\\``), ``alembic upgrade head``, the worker with
``--schedule`` (see ``worker.scheduler.PollScheduler``), the API on
``--api-port`` (default 8000), and the web app on ``--web-port`` (default
3000, pinned with ``next dev -- -p <port>`` and verified against the
child's own ready-log line -- see ``_wait_web_ready`` -- rather than
trusting that *something* answers on that port, which a stray unrelated
process could satisfy just as well as our own web server), then opens
``http://localhost:<web-port>`` in the default browser. ``down`` stops
everything this script started, cleanly, and never stops a PostgreSQL
server it did not start. ``status`` reports each process's up/down state
(including the port each of api/web actually bound, read from the run-dir
state file -- ``status``/``down``/``logs`` never need ``--web-port``/
``--api-port`` themselves) plus the last poll per source (from
``source_poll_runs``). ``logs`` tails what it started.

``--web-port``/``--api-port`` exist because this machine's port 3000/8000
is not reserved for OpportunityOS -- another, unrelated dev server already
holding 3000 is ordinary, and the founder must be able to proceed without
killing their other work. Overriding the port never reintroduces the
silent-fallback defect the pinning above fixed: an explicit
``--web-port 3005`` still fails loudly (naming both the flag and the port)
if 3005 is occupied, and ``_wait_web_ready`` still verifies the child bound
exactly that port.

If ``--api-port`` is non-default, the web dev server's own child process
gets ``OPPORTUNITYOS_API_PORT`` set to it in its environment (see
``ENV_API_PORT`` below) -- but ``web/next.config.ts`` (out of this
deliverable's file scope; owned by D7) still hardcodes the ``/api/:path*``
rewrite destination as ``http://localhost:8000`` and does not read that
variable yet. Until it does, a non-default ``--api-port`` starts the API
server on the requested port but the web app's same-origin ``/api/*``
proxy still targets 8000.

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
import re
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

#: Every value in docs/templates/alpha.env.template contains this marker
#: (e.g. REPLACE_WITH_A_LOCAL_FOUNDER_PASSWORD). A founder who copies the
#: template to private/alpha.env but forgets to edit it must never reach
#: PostgreSQL detection or `alembic upgrade head` with an unedited value --
#: those fail with a raw SQLAlchemy/psycopg2 traceback that does not say
#: what is actually wrong. load_alpha_env checks for this marker itself.
PLACEHOLDER_MARKER = "REPLACE_WITH_"

API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 3000
PG_HOST = "127.0.0.1"
PG_PORT = 5432

#: Environment variable set on the web dev server's process so a future
#: web/next.config.ts change can read it for the `/api/:path*` rewrite
#: target instead of the hardcoded `http://localhost:8000` it has today.
#: alpha.py always sets this to the resolved --api-port; next.config.ts
#: does not read it yet (that file is out of this deliverable's scope --
#: see this module's docstring for the exact contract expected of it).
ENV_API_PORT = "OPPORTUNITYOS_API_PORT"

_PROCESS_LABELS = ("worker", "api", "web")


class AlphaError(RuntimeError):
    """Any ``up``/``down``/``status`` failure, with a founder-readable message."""


# ---------------------------------------------------------------------------
# private/alpha.env
# ---------------------------------------------------------------------------


def load_alpha_env(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from ``path``. Raises ``AlphaError`` with a
    clear, actionable message if the file is missing, incomplete, or still
    contains unedited template placeholders (``PLACEHOLDER_MARKER``) -- the
    most common first mistake with any env template, and one that would
    otherwise surface as a raw SQLAlchemy/psycopg2 connection traceback out
    of ``alembic upgrade head`` instead of a message that says what is
    actually wrong. All three checks happen here, before ``up`` ever
    touches PostgreSQL detection or migrations.
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

    # Checked before the missing-key check below: a freshly-copied,
    # unedited template has every key present (so "missing" would say
    # nothing is wrong) but every value is still a placeholder -- this is
    # the actual common case, so it must be the first, most specific error
    # a founder sees, naming every unedited key at once rather than one per
    # re-run.
    placeholder_keys = sorted(key for key, value in values.items() if PLACEHOLDER_MARKER in value)
    if placeholder_keys:
        raise AlphaError(
            f"{path} still contains template placeholders for {', '.join(placeholder_keys)}. Edit "
            "that file and replace every REPLACE_WITH_* value, then retry `up`."
        )

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


#: Matches Next dev's own ready line, e.g. "- Local:         http://localhost:3001"
#: (see node_modules/next/dist/server/lib/app-info-log.js: `_log.bootstrap('- Local:         ${appUrl}')`).
_NEXT_LOCAL_URL_RE = re.compile(r"-\s*Local:\s*https?://[^:/\s]+:(\d+)")


def _read_log_since(log_path: Path, offset: int) -> str:
    """Return only the bytes written to ``log_path`` at or after ``offset``.

    ``web.log`` is opened in append mode (see ``_spawn``) and survives
    across every ``up`` attempt, so a stale ready line from a *previous*
    run (a different port, possibly still sitting at the top of the file)
    must never be visible to a fresh spawn's own readiness check --
    otherwise the very first "- Local:" match found is whichever run wrote
    it first, not this run's.
    """
    if not log_path.exists():
        return ""
    with open(log_path, "rb") as handle:
        handle.seek(offset)
        return handle.read().decode("utf-8", errors="replace")


#: Next prints exactly this line (see next/dist/cli/next-dev.js) when a
#: second dev server for the same project directory (web/.next/dev/lock)
#: starts up: it briefly prints its own ready line, notices the lock, prints
#: this banner plus the *existing* server's own "- Local:"/"- PID:" lines,
#: and exits. See _diagnose_web_exit's docstring.
_ALREADY_RUNNING_MARKER = "Another next dev server is already running"

_PID_LINE_RE = re.compile(r"-\s*PID:\s*(\d+)")


def _parse_already_running_block(text: str) -> Optional[tuple[Optional[str], Optional[str]]]:
    """Return ``(existing_port, existing_pid)`` parsed from Next's own
    "Another next dev server is already running" banner, or None if that
    banner is not present anywhere in ``text``. Only the few lines
    immediately following the banner are scanned, mirroring exactly how
    Next itself prints the block (banner, then "- Local:", then "- PID:").
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _ALREADY_RUNNING_MARKER not in line:
            continue
        existing_port: Optional[str] = None
        existing_pid: Optional[str] = None
        for follow in lines[i + 1 : i + 6]:
            if existing_port is None:
                port_match = _NEXT_LOCAL_URL_RE.search(follow)
                if port_match:
                    existing_port = port_match.group(1)
            if existing_pid is None:
                pid_match = _PID_LINE_RE.search(follow)
                if pid_match:
                    existing_pid = pid_match.group(1)
        if existing_port or existing_pid:
            return existing_port, existing_pid
    return None


def _diagnose_web_exit(proc: "subprocess.Popen", log_path: Path, text: str, expected_port: int) -> AlphaError:
    """Build the error for a web child that has exited -- either right away,
    or (see ``_wait_web_ready``) after printing a ready line that turned out
    not to mean it was actually serving anything. Never returns normally;
    always returns an ``AlphaError`` for the caller to raise (a plain
    function, not `raise` itself, so callers can add their own context if
    ever needed without a bare re-raise).

    Checked first: Next 16 allows only one dev server per project directory
    (it holds a lock at ``web/.next/dev/lock``); a second one prints its own
    ready line, then notices the existing lock, prints "Another next dev
    server is already running" plus the *existing* server's own port/pid,
    and exits. A founder who left a dev server running from an earlier
    session (or their editor) will hit exactly this, and Next has already
    diagnosed it precisely -- surfacing that verbatim (naming the existing
    pid/port) beats a generic "the child exited" that would leave them
    guessing at something already known.
    """
    already_running = _parse_already_running_block(text)
    if already_running is not None:
        existing_port, existing_pid = already_running
        where_bits = []
        if existing_pid:
            where_bits.append(f"pid {existing_pid}")
        if existing_port:
            where_bits.append(f"port {existing_port}")
        where = " on ".join(where_bits) if where_bits else "another process"
        return AlphaError(
            f"Next detected another dev server already running for this project ({where}) and exited "
            "-- Next allows only one dev server per project directory (it holds a lock at "
            f"web/.next/dev/lock). The process just spawned for this `up` (pid {proc.pid}) briefly "
            f"printed a ready line for port {expected_port} before Next noticed that lock and shut it "
            "down again; it was never actually serving anything. Stop the pre-existing dev server "
            f"yourself (e.g. a session left running from an earlier `up` outside this alpha session, "
            f"or from an editor/IDE), or pass `--web-port` to use a different port. See {log_path} for "
            "the full log."
        )
    tail = "\n".join(text.strip().splitlines()[-20:])
    return AlphaError(
        f"web dev server (pid {proc.pid}) reported it was ready on port {expected_port} but then exited "
        f"(exit code {proc.returncode}) before this could confirm it was actually accepting connections "
        f"-- a ready line in the log is not proof by itself. See {log_path}. Last lines:\n{tail}"
    )


def _wait_web_ready(
    proc: "subprocess.Popen",
    log_path: Path,
    expected_port: int,
    timeout_seconds: float,
    *,
    log_offset: int = 0,
) -> None:
    """Wait for the web dev server to report ready, then verify it actually
    bound ``expected_port`` -- not just that *something* answers there --
    and is still genuinely serving it, not just that a ready line was
    printed at some point.

    Next's dev server, when its requested port is free to auto-retry (i.e.
    no explicit ``-p`` was passed, or a race let it start before this
    module's own preflight check), silently falls back to the next free
    port and only warns about it in its own stdout -- it does not fail the
    process. That previously let ``alpha.py`` report and open
    "http://localhost:3000" while the web tier was actually listening on
    3001 and an unrelated process answered on 3000 instead: the health
    check only asked "does *something* answer on 3000?", which a stray,
    unrelated process satisfied. ``cmd_up`` pins the port with
    ``next dev -- -p <port>`` so Next itself refuses to silently fall back
    (see next/dist/cli/next-dev.js: ``allowRetry = portSource === 'default'``,
    which is false once ``-p`` is explicit) and instead exits non-zero on
    EADDRINUSE -- caught below via ``proc.poll()``. This function is the
    second, independent check: it parses the child's own "- Local:
    http://host:PORT" ready line out of its log and compares that port to
    ``expected_port``, so a mismatch is caught even if the pin above is
    ever bypassed (e.g. a future Next version, or a differently-invoked
    dev server) rather than trusting an external TCP probe alone.

    A *third*, independent problem this function also closes: Next allows
    only one dev server per project directory. A second one (this one, if
    the founder left an earlier dev server running) briefly binds the
    requested port, prints a completely correct-looking "- Local:
    http://host:PORT" ready line, *then* notices the existing lock and
    exits. Matching that ready line is therefore not proof of anything by
    itself -- after a match, this function keeps polling until it can
    additionally confirm the process is still alive (``proc.poll() is
    None``) AND a real TCP connect to the port succeeds, before reporting
    success. If the process exits after a match instead, ``_diagnose_web_exit``
    distinguishes the "another dev server" case (named precisely, since
    Next already diagnosed it) from any other post-ready exit.

    ``log_offset`` is the byte size of ``log_path`` immediately before this
    spawn (0 if it did not exist yet). ``web.log`` is append-only across
    every ``up`` attempt (see ``_spawn``), so without this offset the first
    "- Local:" line anywhere in the file -- which could be from an earlier
    run, at a different port -- would win the match instead of the line
    *this* spawn actually wrote, causing a spurious mismatch failure (or a
    spurious pass) against stale content. ``cmd_up`` records this offset
    with ``log_path.stat().st_size`` right before calling ``_spawn``.
    """
    deadline = time.monotonic() + timeout_seconds
    matched = False
    while time.monotonic() < deadline:
        exited = proc.poll() is not None
        text = _read_log_since(log_path, log_offset)

        if exited and not matched:
            raise AlphaError(
                f"web (npm run dev) exited immediately (exit code {proc.returncode}) while starting on "
                f"port {expected_port} -- port {expected_port} is likely already in use by another "
                f"process. Run `python scripts/alpha.py down` if a previous alpha session left it "
                f"running, or pass `--web-port` to use a different one, then retry `up`. See {log_path} "
                "for details."
            )

        if not matched:
            match = _NEXT_LOCAL_URL_RE.search(text)
            if match:
                actual_port = int(match.group(1))
                if actual_port != expected_port:
                    raise AlphaError(
                        f"web dev server bound port {actual_port} instead of the required "
                        f"{expected_port} (see {log_path}) -- another process is already holding "
                        f"port {expected_port}. Run `python scripts/alpha.py down` if a previous alpha "
                        f"session left it running, or pass `--web-port` to use a different one, then "
                        "retry `up`."
                    )
                matched = True

        if matched:
            # A ready line is not proof by itself -- see this function's own
            # docstring on the "another dev server" case. Only report
            # success once the process is still alive AND the port is
            # actually accepting connections; if it has exited instead,
            # diagnose exactly why (re-reading the log first, so a banner
            # written in the same instant the process exits is not missed).
            if proc.poll() is not None:
                raise _diagnose_web_exit(proc, log_path, _read_log_since(log_path, log_offset), expected_port)
            if _port_open(WEB_HOST, expected_port, timeout=0.5):
                return

        time.sleep(0.3)

    if matched:
        raise AlphaError(
            f"Timed out after {timeout_seconds:.0f}s confirming the web dev server (pid {proc.pid}) is "
            f"actually accepting connections on port {expected_port} after it reported ready. See "
            f"{log_path}."
        )
    raise AlphaError(
        f"Timed out after {timeout_seconds:.0f}s waiting for the web dev server to report it is ready "
        f"on port {expected_port}. See {log_path}."
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


def _is_zombie(pid: int) -> bool:
    """Linux-only: True if ``pid`` is a zombie (exited, not yet reaped).

    ``os.kill(pid, 0)`` succeeds for a zombie exactly as it does for a live
    process -- its process-table entry still exists even though it holds no
    port and does no work -- so without this, a pid this module just killed
    (see ``_kill_pid_tree``) would be reported alive by ``_pid_alive``
    indefinitely, until *something* reaps it. Not portable beyond Linux (no
    ``/proc`` on macOS), which matches this project's actual platforms
    (Windows via ``_pid_alive``'s own separate branch, Linux in CI).
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False  # /proc unavailable, or pid vanished between checks -- not "definitely a zombie"
    # Field 2 (comm) is parenthesised and may itself contain ")" (e.g. a
    # command named "a)b") -- split on the *last* ")" to get past it
    # safely, exactly as `man proc` recommends for parsing this format.
    after_comm = raw.rsplit(")", 1)[-1].split()
    return bool(after_comm) and after_comm[0] == "Z"


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout

    # Reap it first, if this process happens to be pid's parent: without
    # this, a child this process itself spawned (via _spawn) and then
    # killed (via _kill_pid_tree) would sit as a zombie -- os.kill(pid, 0)
    # below succeeds for a zombie too -- and be reported alive forever,
    # since nothing else will ever reap it. WNOHANG never blocks; ECHILD
    # means this process is not pid's parent (e.g. `status`/`down` run in a
    # fresh shell well after the `up` that originally spawned pid already
    # exited) and is the expected, common case, not an error.
    try:
        reaped_pid, _ = os.waitpid(pid, os.WNOHANG)
        if reaped_pid == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass

    try:
        os.kill(pid, 0)
    except OSError:
        return False

    # Reaped above if this process was pid's parent; otherwise (a fresh
    # `status`/`down` process, not pid's parent) reaping is impossible, so
    # a zombie left behind by pid's *real* parent must be detected instead
    # of trusted as "alive" -- see _is_zombie's own docstring.
    if _is_zombie(pid):
        return False
    return True


def _kill_pid_tree(pid: int) -> None:
    """Kill ``pid`` and its children -- npm/uvicorn spawn child processes that
    would otherwise be left holding ports 8000/3000 after ``down``.

    On POSIX, ``_spawn`` starts every tracked child with ``start_new_session
    =True`` (``setsid``), making it the leader of its own new process group
    (pgid == its own pid). That is what makes killing the *group* here --
    ``os.killpg``, not a plain ``os.kill(pid, SIGTERM)`` on the tracked pid
    alone -- actually reach npm's own children: the Next process npm execs
    or forks, and Next's own dev-server child underneath that. A bare
    ``os.kill`` on only the tracked pid (the previous behaviour) never
    signalled any of them, so they were left holding ports 3000/8000 after
    `down` -- the exact same orphan-survivor defect already fixed for
    Windows via ``taskkill /T /F``, silently still present on POSIX behind
    a docstring that claimed otherwise.

    Escalates from SIGTERM to SIGKILL if the group has not exited within a
    short bounded wait: signalling a group does not itself block until
    every member has actually exited, and ``_stop_processes``'s own
    subsequent port-freed check (``_wait_port_freed``) assumes this
    function does not return before giving the signal a real chance to
    take effect.

    Only ever called on a pid this module itself spawned via ``_spawn``
    (the ``start_new_session=True`` contract above depends on that): a
    pid that shares its caller's own process group -- any ordinary
    ``subprocess.Popen`` without that flag -- must never be passed here,
    since ``os.killpg`` would then signal the *caller's* group too.
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return

    import signal as _signal

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return  # already gone

    def _signal_group(sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass

    def _wait_for_exit(timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                reaped_pid, _ = os.waitpid(pid, os.WNOHANG)
                if reaped_pid == pid:
                    return True
            except ChildProcessError:
                pass  # not this process' child -- fall back to a direct liveness check
            if not _pid_alive(pid):
                return True
            time.sleep(0.1)
        return not _pid_alive(pid)

    _signal_group(_signal.SIGTERM)
    if _wait_for_exit(5.0):
        return

    _signal_group(_signal.SIGKILL)
    _wait_for_exit(3.0)


def _spawn(cmd: list[str], cwd: Path, env: dict, log_path: Path) -> "subprocess.Popen":
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab")
    try:
        popen_kwargs: dict = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # Leader of its own new process group (pgid == its own pid) --
            # required by _kill_pid_tree's os.killpg-based teardown above,
            # so npm's own children (not just npm itself) are reachable.
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **popen_kwargs,
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


def _stop_postgres(pg_info: dict) -> tuple[str, bool]:
    """Returns ``(message, stopped)``. ``stopped`` is True whenever there is
    nothing left for a caller to worry about -- either PostgreSQL was left
    running on purpose (not ours to stop) or ``pg_ctl stop`` actually
    succeeded; False means a caller must not treat this as done (see
    ``cmd_down``/``cmd_up``'s rollback, which keep the state file around
    when this is False so a retry can still reach it).
    """
    if not pg_info or not pg_info.get("started_by_alpha"):
        return "PostgreSQL: left running (alpha.py did not start it).", True
    pg_ctl = pg_info.get("pg_ctl")
    data_dir = pg_info.get("data_dir")
    if not pg_ctl or not data_dir:
        return (
            "PostgreSQL: alpha.py started it but the state file is missing pg_ctl/data_dir; stop it manually.",
            False,
        )
    result = subprocess.run(
        [pg_ctl, "stop", "-D", data_dir, "-m", "fast", "-w", "-t", "30"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return (
            f"PostgreSQL: `pg_ctl stop` failed (exit code {result.returncode}): "
            f"{result.stdout}\n{result.stderr}",
            False,
        )
    return "PostgreSQL: stopped (portable cluster started by alpha.py).", True


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


def _wait_port_freed(host: str, port: int, timeout_seconds: float = 5.0) -> bool:
    """Poll until nothing answers on ``host``:``port``, or ``timeout_seconds`` elapses.

    Returns whether the port is free by the end of the wait. Used after
    ``_kill_pid_tree`` to confirm a kill actually freed the port rather than
    trusting the tracked pid's exit alone -- ``npm run dev`` spawns Next,
    which spawns its own dev server process; a grandchild can be reparented
    (Windows job objects aside, this has been observed in practice) and
    survive ``taskkill /PID <npm-pid> /T /F`` while still holding the port.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _port_open(host, port, timeout=0.5):
            return True
        time.sleep(0.3)
    return not _port_open(host, port, timeout=0.5)


def _stop_processes(processes: dict, *, port_freed_timeout: float = 5.0) -> tuple[list[str], bool]:
    """Kill every tracked pid, then verify each one's recorded port is
    actually free (not just that the tracked pid is gone -- see
    ``_wait_port_freed``). Returns ``(messages, all_stopped)``; a caller
    must not discard state (or report success) while ``all_stopped`` is
    False, since that is exactly what stranded a survivor with no way for a
    later ``down`` to reach it.

    ``port_freed_timeout`` is exposed (default 5s in production use) purely
    so tests can bound how long a genuinely-still-occupied-port case takes
    to fail, without changing production's bounded-but-real wait.
    """
    messages: list[str] = []
    all_stopped = True
    for label, info in processes.items():
        pid = info.get("pid")
        if pid is not None:
            if _pid_alive(pid):
                _kill_pid_tree(pid)
                messages.append(f"{label}: stopped (was pid {pid}).")
            else:
                messages.append(f"{label}: already stopped (pid {pid} not running).")

        port = info.get("port")
        if port is None:
            continue
        # All of this project's own services bind 127.0.0.1 only (API_HOST
        # == WEB_HOST == "127.0.0.1"); a single host is used here rather
        # than threading a per-label host through, since there is only one.
        if not _wait_port_freed("127.0.0.1", port, timeout_seconds=port_freed_timeout):
            all_stopped = False
            messages.append(
                f"{label}: WARNING -- pid {pid} was stopped but port {port} is still occupied "
                "(npm/Next can reparent a grandchild that then survives killing the tracked pid). "
                f"Find and stop whatever is still listening on {port} yourself, e.g. "
                f"`netstat -ano | findstr :{port}` on Windows, then re-run `python scripts/alpha.py down`."
            )
    return messages, all_stopped


# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------


def cmd_up(
    env_file: Path,
    run_dir: Path,
    *,
    web_port: int = DEFAULT_WEB_PORT,
    api_port: int = DEFAULT_API_PORT,
) -> int:
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
        # uvicorn never silently rebinds on a busy port (unlike Next's dev
        # server -- see _wait_web_ready's docstring); it errors and exits
        # non-zero, which the preflight check plus _wait_process_alive below
        # already turn into a loud, immediate failure. A preflight check is
        # still added here (mirroring the web one) so that failure is
        # reported before ever spawning uvicorn, with a message naming
        # --api-port, rather than relying on the exit-code path alone.
        if _port_open(API_HOST, api_port, timeout=1.0):
            raise AlphaError(
                f"Port {api_port} is already in use by another process, so the API server cannot bind "
                f"it. Run `python scripts/alpha.py down` if a previous alpha session left it running, "
                f"or pass `--api-port` to use a different one, then retry `up`."
            )
        api_proc = _spawn(
            [sys.executable, "-m", "uvicorn", "api.app:app", "--host", API_HOST, "--port", str(api_port)],
            REPO_ROOT,
            env,
            api_log,
        )
        processes["api"] = {"pid": api_proc.pid, "log": str(api_log), "port": api_port}
        _wait_process_alive(api_proc, 2.0, "API server", api_log)
        _wait_for_port(API_HOST, api_port, 30.0, "the API server")
        print(f"API: listening on {API_HOST}:{api_port} (pid {api_proc.pid}), logging to {api_log}.")

        if not (WEB_DIR / "node_modules").exists():
            raise AlphaError(
                f"{WEB_DIR / 'node_modules'} is missing. Run `npm install` in {WEB_DIR} once, then "
                "re-run `python scripts/alpha.py up`."
            )

        # Fail loudly, before ever spawning npm, if the web port is already
        # taken -- a clear, immediate message (naming --web-port) beats
        # waiting on Next's own startup (or _wait_web_ready's log-parsing
        # check below) to surface it.
        if _port_open(WEB_HOST, web_port, timeout=1.0):
            raise AlphaError(
                f"Port {web_port} is already in use by another process, so the web dev server cannot "
                f"bind it. Run `python scripts/alpha.py down` if a previous alpha session left it "
                f"running, or pass `--web-port` to use a different one, then retry `up`."
            )

        # alpha.py must run the web app against the real API, never the MSW
        # mock -- drop any inherited NEXT_PUBLIC_USE_MOCK_API=1 rather than
        # trust the founder's ambient shell not to have it set from other work.
        web_env = os.environ.copy()
        web_env.pop("NEXT_PUBLIC_USE_MOCK_API", None)
        # See ENV_API_PORT's own docstring: web/next.config.ts does not read
        # this yet (out of this deliverable's scope -- owned by D7), but the
        # value is set unconditionally so wiring the config side later is a
        # config-only change with nothing to add here.
        web_env[ENV_API_PORT] = str(api_port)
        web_log = run_dir / "logs" / "web.log"
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        # `-- -p <port>` pins the port explicitly: Next's dev server only
        # silently falls back to another port when the port came from its own
        # default (see _wait_web_ready's docstring) -- an explicit -p instead
        # makes it exit non-zero on EADDRINUSE, which _wait_web_ready treats
        # as a loud, immediate failure rather than a silent port switch. This
        # holds for any --web-port value, not just the default 3000.
        # web.log is append-only across every `up` attempt (see _spawn), so a
        # stale "- Local:" line from a previous run must not be visible to
        # this run's own readiness check -- record the size right before
        # spawning and only look at bytes written from here on.
        web_log_offset = web_log.stat().st_size if web_log.exists() else 0
        web_proc = _spawn([npm_cmd, "run", "dev", "--", "-p", str(web_port)], WEB_DIR, web_env, web_log)
        processes["web"] = {"pid": web_proc.pid, "log": str(web_log), "port": web_port}
        _wait_web_ready(web_proc, web_log, web_port, 60.0, log_offset=web_log_offset)
        print(f"Web: listening on {WEB_HOST}:{web_port} (pid {web_proc.pid}), logging to {web_log}.")

        state = {
            "processes": processes,
            "postgres": pg_info,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(run_dir, state)

        url = f"http://localhost:{web_port}"
        print(f"Opening {url} ...")
        try:
            webbrowser.open(url)
        except Exception:
            pass

        print("alpha: up.")
        return 0
    except AlphaError as exc:
        print(f"alpha up: FAILED: {exc}", file=sys.stderr)
        rollback_confirmed = True
        if processes or pg_info:
            print("alpha up: rolling back anything this run started ...", file=sys.stderr)
            process_messages, processes_confirmed = _stop_processes(processes)
            for message in process_messages:
                print(message, file=sys.stderr)
            rollback_confirmed = rollback_confirmed and processes_confirmed
            if pg_info:
                pg_message, pg_confirmed = _stop_postgres(pg_info)
                print(pg_message, file=sys.stderr)
                rollback_confirmed = rollback_confirmed and pg_confirmed
        if rollback_confirmed:
            _clear_state(run_dir)
        else:
            # Rollback could not confirm everything is actually gone (see
            # _stop_processes' port-freed check) -- discarding the state
            # file here is exactly what previously stranded a survivor with
            # no way for a later `down` to reach it. Persist it instead so
            # `down`, run later from a fresh shell, can still find and
            # finish the cleanup.
            _save_state(
                run_dir,
                {
                    "processes": processes,
                    "postgres": pg_info,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            print(
                "alpha up: rollback could NOT confirm everything stopped -- state was kept (not "
                "cleared) so it can be retried. Run `python scripts/alpha.py down` to finish cleanup.",
                file=sys.stderr,
            )
        return 1


# ---------------------------------------------------------------------------
# down
# ---------------------------------------------------------------------------


def cmd_down(run_dir: Path) -> int:
    state = _load_state(run_dir)
    if not state:
        print(f"alpha: no session recorded under {run_dir} (nothing to stop).")
        return 0

    process_messages, processes_confirmed = _stop_processes(state.get("processes", {}))
    for message in process_messages:
        print(message)

    pg_message, pg_confirmed = _stop_postgres(state.get("postgres", {}))
    print(pg_message)

    if processes_confirmed and pg_confirmed:
        _clear_state(run_dir)
        print("alpha: down.")
        return 0

    # Something is still confirmed running (see the WARNING line(s) above) --
    # the state file is deliberately left in place (not cleared) so this can
    # be retried, instead of reporting success and then having nothing left
    # to point `down` at the survivor next time.
    print(
        "alpha: down incomplete -- see the WARNING(s) above. State was left in place; resolve them "
        "and re-run `python scripts/alpha.py down`."
    )
    return 1


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
            port = info.get("port")
            port_suffix = f", port {port}" if port else ""
            print(f"  {label}: up (pid {info['pid']}{port_suffix})")
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
    parser.add_argument(
        "--web-port",
        type=int,
        default=DEFAULT_WEB_PORT,
        help=(
            f"Port for the web dev server (default: {DEFAULT_WEB_PORT}). Only meaningful for `up` -- "
            "the port actually used is recorded in the run-dir state file, so `status`/`down`/`logs` "
            "read it back from there and never need this flag repeated. Use this when the default "
            "port is already held by an unrelated process on this machine; `up` still fails loudly "
            "(never silently falls back) if the port you pass here is also occupied."
        ),
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=DEFAULT_API_PORT,
        help=(
            f"Port for the API server (default: {DEFAULT_API_PORT}). Only meaningful for `up`; see "
            f"--web-port for the state-file/fail-loudly behaviour, which is identical. Also sets "
            f"{ENV_API_PORT} in the web dev server's own environment, for a future web/next.config.ts "
            "change to read for its /api/* rewrite target -- next.config.ts does not read it yet."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.command == "up":
        return cmd_up(args.env_file, args.run_dir, web_port=args.web_port, api_port=args.api_port)
    if args.command == "down":
        return cmd_down(args.run_dir)
    if args.command == "status":
        return cmd_status(args.env_file, args.run_dir)
    if args.command == "logs":
        return cmd_logs(args.run_dir)
    return 2  # unreachable: argparse's `choices` already rejects anything else


if __name__ == "__main__":
    raise SystemExit(main())
