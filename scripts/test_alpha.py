"""Tests for scripts/alpha.py.

Never reads/writes private/: every test passes an explicit --env-file (or
calls load_alpha_env directly) pointing at a tempfile, never the real
private/alpha.env. --run-dir is likewise always a tempdir, so these tests
never touch the real out/alpha_run/ state either.

Does not start the real web or API: only status/down/helper-level behaviour
is exercised (per the deliverable's own instruction: "safe to run when
nothing is up. Do not start the real web or API in unit tests").
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import scripts.alpha as alpha

REPO_ROOT = Path(__file__).resolve().parents[1]
ALPHA_SCRIPT = REPO_ROOT / "scripts" / "alpha.py"


class TestLoadAlphaEnv(unittest.TestCase):
    def test_missing_file_names_the_template_and_the_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist" / "alpha.env"
            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha.load_alpha_env(missing)
            self.assertIn("alpha.env.template", str(ctx.exception))
            self.assertIn(str(missing), str(ctx.exception))

    def test_parses_a_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text(
                "# a comment line\n"
                "\n"
                "OPPORTUNITYOS_FOUNDER_PASSWORD=hunter2\n"
                "OPPORTUNITYOS_SESSION_SECRET=abc123\n"
                'OPPORTUNITYOS_DB_URL="postgresql+psycopg2://u:p@127.0.0.1:5432/db"\n',
                encoding="utf-8",
            )
            values = alpha.load_alpha_env(env_path)
            self.assertEqual(values["OPPORTUNITYOS_FOUNDER_PASSWORD"], "hunter2")
            self.assertEqual(values["OPPORTUNITYOS_SESSION_SECRET"], "abc123")
            # Surrounding quotes are stripped.
            self.assertEqual(values["OPPORTUNITYOS_DB_URL"], "postgresql+psycopg2://u:p@127.0.0.1:5432/db")

    def test_missing_required_key_is_reported_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text("OPPORTUNITYOS_FOUNDER_PASSWORD=hunter2\n", encoding="utf-8")
            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha.load_alpha_env(env_path)
            self.assertIn("OPPORTUNITYOS_SESSION_SECRET", str(ctx.exception))
            self.assertIn("OPPORTUNITYOS_DB_URL", str(ctx.exception))

    def test_malformed_line_is_reported_with_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text("not_a_key_value_line\n", encoding="utf-8")
            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha.load_alpha_env(env_path)
            self.assertIn(f"{env_path}:1:", str(ctx.exception))


class TestStateFile(unittest.TestCase):
    def test_save_load_clear_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.assertEqual(alpha._load_state(run_dir), {})
            alpha._save_state(run_dir, {"processes": {"worker": {"pid": 123, "log": "x.log"}}})
            loaded = alpha._load_state(run_dir)
            self.assertEqual(loaded["processes"]["worker"]["pid"], 123)
            alpha._clear_state(run_dir)
            self.assertEqual(alpha._load_state(run_dir), {})

    def test_load_state_tolerates_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text("not json{{{", encoding="utf-8")
            self.assertEqual(alpha._load_state(run_dir), {})


class TestPortHelpers(unittest.TestCase):
    def test_port_open_true_for_a_listening_socket(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            self.assertTrue(alpha._port_open("127.0.0.1", port, timeout=1.0))
        finally:
            srv.close()

    def test_wait_for_port_times_out_with_a_clear_message(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.close()  # now definitely closed
        with self.assertRaises(alpha.AlphaError) as ctx:
            alpha._wait_for_port("127.0.0.1", port, 0.5, "a test service")
        self.assertIn("Timed out", str(ctx.exception))
        self.assertIn("a test service", str(ctx.exception))
        self.assertIn(str(port), str(ctx.exception))


class TestWaitWebReady(unittest.TestCase):
    """Regression coverage for the "reported port != actually bound port" defect.

    A real ``python`` subprocess stands in for the web child here -- never
    the real ``npm``/``next`` (per this module's own "do not start the real
    web ... in unit tests" instruction) -- because the behaviour under test
    is entirely about parsing the child's log and comparing the port found
    there to the port we asked for; it does not depend on Next specifically.

    Before ``_wait_web_ready`` existed, ``cmd_up`` only checked "does
    *something* answer on WEB_PORT" (``_wait_for_port``), which a stray,
    unrelated process already listening on that port would satisfy just as
    well as the real web child -- exactly the failure this class pins down.
    """

    def _spawn_long_lived(self) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    def _spawn_immediately_exiting(self, exit_code: int = 1) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", f"import sys; sys.exit({exit_code})"])
        proc.wait(timeout=5)
        return proc

    def test_raises_when_the_child_bound_a_different_port_than_requested(self):
        """The defect this project actually hit: Next fell back to 3001 while
        alpha.py had told the founder 3000 was ready. A test that would fail
        against the old ``_wait_for_port``-only behaviour (which only checks
        that *a* listener exists on the expected port, not that our own
        child is the one that bound it).
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  ▲ Next.js 16.3.4\n"
                "  - Local:         http://localhost:3001\n"
                "  - Network:       http://192.168.1.5:3001\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=3000, timeout_seconds=5)
                message = str(ctx.exception)
                self.assertIn("3001", message)
                self.assertIn("3000", message)
                self.assertIn("bound", message)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_returns_cleanly_when_the_child_bound_the_expected_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  ▲ Next.js 16.3.4\n"
                "  - Local:         http://localhost:3000\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                # Must not raise.
                alpha._wait_web_ready(proc, log_path, expected_port=3000, timeout_seconds=5)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_raises_when_the_child_exits_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"  # never written -- child exited before logging anything
            proc = self._spawn_immediately_exiting(exit_code=1)
            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha._wait_web_ready(proc, log_path, expected_port=3000, timeout_seconds=5)
            message = str(ctx.exception)
            self.assertIn("exited immediately", message)
            self.assertIn("3000", message)

    def test_times_out_with_a_clear_message_if_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"  # never written
            proc = self._spawn_long_lived()
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=3000, timeout_seconds=1)
                message = str(ctx.exception)
                self.assertIn("Timed out", message)
                self.assertIn("3000", message)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    # -- --web-port override path: same shape, non-default port -----------------

    def test_honours_a_non_default_expected_port_end_to_end(self):
        """`--web-port 3005` must be verified exactly like the default: the
        child reporting 3005 in its own ready line must be accepted.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                "  - Local:         http://localhost:3005\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                # Must not raise.
                alpha._wait_web_ready(proc, log_path, expected_port=3005, timeout_seconds=5)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_raises_on_a_mismatch_against_a_non_default_expected_port(self):
        """The override must not weaken the guarantee: even when the founder
        asked for a non-default port, a child that bound a *different* port
        still has to be rejected loudly rather than accepted because it is
        "close enough" to what was requested.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                "  - Local:         http://localhost:3006\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=3005, timeout_seconds=5)
                message = str(ctx.exception)
                self.assertIn("3006", message)
                self.assertIn("3005", message)
                self.assertIn("bound", message)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    # -- log_offset: web.log is append-only across `up` attempts ----------------

    def test_ignores_a_stale_local_line_written_before_this_spawns_offset(self):
        """The real defect this project hit on a second `up`: web.log is
        opened in append mode and survives across attempts, so a stale
        "- Local:" line from an *earlier* run (a different port) sits
        before this run's own line. Without log_offset, the first match in
        the whole file wins -- the stale one -- producing a confident,
        specific, wrong "bound the wrong port" failure on a run that
        actually succeeded. This test fails against a call that omits
        log_offset (i.e. today's default of 0), and passes once the byte
        offset recorded right before spawning is threaded through.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            # A previous, unrelated `up` attempt's own ready line.
            log_path.write_text(
                "  Next.js 16.3.4\n"
                "  - Local:         http://localhost:3001\n",
                encoding="utf-8",
            )
            log_offset = log_path.stat().st_size  # recorded "immediately before this spawn"
            # This run's own line, appended after the offset was captured --
            # exactly what _spawn's append-mode open produces in practice.
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("  Next.js 16.3.4\n")
                handle.write("  - Local:         http://localhost:3210\n")

            proc = self._spawn_long_lived()
            try:
                # Must not raise: 3210 (after the offset) matches what was
                # requested; the stale 3001 line (before the offset) must
                # never be considered.
                alpha._wait_web_ready(
                    proc, log_path, expected_port=3210, timeout_seconds=5, log_offset=log_offset
                )
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_without_the_offset_the_stale_line_causes_a_false_failure(self):
        """Documents the defect directly: the same log/ports as the test
        above, but called without log_offset (today's default, 0) -- the
        stale 3001 line wins and a perfectly successful 3210 bind is
        reported as a mismatch.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                "  - Local:         http://localhost:3001\n",
                encoding="utf-8",
            )
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("  Next.js 16.3.4\n")
                handle.write("  - Local:         http://localhost:3210\n")

            proc = self._spawn_long_lived()
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=3210, timeout_seconds=5)
                self.assertIn("3001", str(ctx.exception))
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)


class TestPortOverrideCli(unittest.TestCase):
    """--web-port/--api-port must actually reach cmd_up, with correct defaults."""

    def test_defaults_when_not_specified(self):
        args = alpha.build_arg_parser().parse_args(["up"])
        self.assertEqual(args.web_port, alpha.DEFAULT_WEB_PORT)
        self.assertEqual(args.api_port, alpha.DEFAULT_API_PORT)

    def test_parser_accepts_explicit_overrides(self):
        args = alpha.build_arg_parser().parse_args(
            ["up", "--web-port", "3005", "--api-port", "8080"]
        )
        self.assertEqual(args.web_port, 3005)
        self.assertEqual(args.api_port, 8080)

    def test_main_threads_the_overrides_into_cmd_up(self):
        with mock.patch.object(alpha, "cmd_up", return_value=0) as cmd_up_mock:
            exit_code = alpha.main(["up", "--web-port", "3005", "--api-port", "8080"])
        self.assertEqual(exit_code, 0)
        cmd_up_mock.assert_called_once()
        _, call_kwargs = cmd_up_mock.call_args
        self.assertEqual(call_kwargs["web_port"], 3005)
        self.assertEqual(call_kwargs["api_port"], 8080)

    def test_main_threads_the_defaults_into_cmd_up_when_unspecified(self):
        with mock.patch.object(alpha, "cmd_up", return_value=0) as cmd_up_mock:
            alpha.main(["up"])
        _, call_kwargs = cmd_up_mock.call_args
        self.assertEqual(call_kwargs["web_port"], alpha.DEFAULT_WEB_PORT)
        self.assertEqual(call_kwargs["api_port"], alpha.DEFAULT_API_PORT)


class TestProcessLifecycleHelpers(unittest.TestCase):
    def test_pid_alive_then_kill_tree_stops_it(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(alpha._pid_alive(proc.pid))
            alpha._kill_pid_tree(proc.pid)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and alpha._pid_alive(proc.pid):
                time.sleep(0.2)
            self.assertFalse(alpha._pid_alive(proc.pid))
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_pid_alive_false_for_an_implausible_pid(self):
        self.assertFalse(alpha._pid_alive(999999999))


class TestStopProcessesPortVerification(unittest.TestCase):
    """Regression coverage for the orphan-survivor defect: killing the
    tracked pid is not sufficient proof the port is free -- npm/Next can
    reparent a grandchild that survives ``taskkill /T``. ``_stop_processes``
    must verify the port itself, not just the tracked pid's exit.
    """

    def test_reports_warning_and_not_all_stopped_when_the_port_stays_occupied(self):
        # A real bound-and-listening socket, actively accepting connections
        # on a background thread, stands in for "the grandchild survivor" --
        # the tracked pid (an implausible one, standing in for "already
        # gone") has nothing to do with what is actually holding the port,
        # exactly like the reported defect. A backlog of 1 with nothing
        # calling accept() would only answer the *first* connect attempt
        # (the OS-level backlog fills and refuses the rest) -- not
        # representative of a real listening server, and not what
        # _wait_port_freed polls with repeatedly -- so this accepts (and
        # immediately drops) connections in a loop for the test's duration.
        survivor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        survivor.bind(("127.0.0.1", 0))
        survivor.listen(5)
        port = survivor.getsockname()[1]
        stop_accepting = threading.Event()

        def _accept_loop():
            survivor.settimeout(0.2)
            while not stop_accepting.is_set():
                try:
                    conn, _ = survivor.accept()
                except socket.timeout:
                    continue
                conn.close()

        accept_thread = threading.Thread(target=_accept_loop, daemon=True)
        accept_thread.start()
        try:
            processes = {"web": {"pid": 999999999, "log": "web.log", "port": port}}
            messages, all_stopped = alpha._stop_processes(processes, port_freed_timeout=1.0)
            self.assertFalse(all_stopped)
            joined = "\n".join(messages)
            self.assertIn("WARNING", joined)
            self.assertIn(str(port), joined)
        finally:
            stop_accepting.set()
            accept_thread.join(timeout=5)
            survivor.close()

    def test_all_stopped_true_when_the_recorded_port_is_actually_free(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.close()  # now genuinely free
        processes = {"web": {"pid": 999999999, "log": "web.log", "port": port}}
        messages, all_stopped = alpha._stop_processes(processes, port_freed_timeout=1.0)
        self.assertTrue(all_stopped)
        self.assertNotIn("WARNING", "\n".join(messages))

    def test_all_stopped_true_for_a_process_with_no_port_to_verify(self):
        # The worker has no port at all -- nothing to verify beyond the pid.
        processes = {"worker": {"pid": 999999999, "log": "worker.log"}}
        messages, all_stopped = alpha._stop_processes(processes)
        self.assertTrue(all_stopped)
        self.assertIn("already stopped", "\n".join(messages))


class TestEnsureAndStopPostgres(unittest.TestCase):
    def test_already_listening_is_detected_and_not_restarted(self):
        with mock.patch.object(alpha, "_port_open", return_value=True):
            result = alpha._ensure_postgres(Path(tempfile.gettempdir()))
        self.assertEqual(result, {"started_by_alpha": False})

    def test_missing_localappdata_raises_a_clear_error(self):
        env_without_localappdata = {k: v for k, v in os.environ.items() if k != "LOCALAPPDATA"}
        with mock.patch.object(alpha, "_port_open", return_value=False):
            with mock.patch.dict(os.environ, env_without_localappdata, clear=True):
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._ensure_postgres(Path(tempfile.gettempdir()))
        self.assertIn("LOCALAPPDATA", str(ctx.exception))

    def test_missing_portable_cluster_raises_a_clear_error_naming_the_brief(self):
        with tempfile.TemporaryDirectory() as fake_localappdata:
            with mock.patch.object(alpha, "_port_open", return_value=False):
                with mock.patch.dict(os.environ, {"LOCALAPPDATA": fake_localappdata}):
                    with self.assertRaises(alpha.AlphaError) as ctx:
                        alpha._ensure_postgres(Path(tempfile.gettempdir()))
        self.assertIn("BRIEF-FR-003.md", str(ctx.exception))

    def test_stop_postgres_leaves_a_server_it_did_not_start(self):
        message, stopped = alpha._stop_postgres({"started_by_alpha": False})
        self.assertIn("did not start it", message)
        self.assertTrue(stopped)

    def test_stop_postgres_calls_pg_ctl_stop_when_alpha_started_it(self):
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            message, stopped = alpha._stop_postgres(
                {"started_by_alpha": True, "pg_ctl": "pg_ctl.exe", "data_dir": "D:/data"}
            )
        self.assertIn("stopped", message)
        self.assertTrue(stopped)
        run_mock.assert_called_once()
        called_cmd = run_mock.call_args[0][0]
        self.assertIn("stop", called_cmd)
        self.assertIn("D:/data", called_cmd)

    def test_stop_postgres_reports_not_stopped_when_pg_ctl_stop_fails(self):
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="pg_ctl: server does not shut down"
            )
            message, stopped = alpha._stop_postgres(
                {"started_by_alpha": True, "pg_ctl": "pg_ctl.exe", "data_dir": "D:/data"}
            )
        self.assertIn("failed", message)
        self.assertFalse(stopped)


class TestCliSmoke(unittest.TestCase):
    """`status` and `down` invoked as real subprocesses, safe when nothing is up.

    Does not start the real web or API: only the CLI's status/down code
    paths run, both of which read process state from an isolated --run-dir
    and never spawn worker/api/web themselves.
    """

    def _run_alpha(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ALPHA_SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )

    def test_status_is_safe_and_exits_zero_when_nothing_is_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_file = Path(tmp) / "no_such_alpha.env"
            result = self._run_alpha("status", "--run-dir", str(run_dir), "--env-file", str(env_file))
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("worker: down", result.stdout)
        self.assertIn("api: down", result.stdout)
        self.assertIn("web: down", result.stdout)
        # Missing env-file must not crash status; it degrades gracefully.
        self.assertIn("unavailable", result.stdout)

    def test_down_is_safe_and_exits_zero_when_nothing_is_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            result = self._run_alpha("down", "--run-dir", str(run_dir))
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("nothing to stop", result.stdout)

    def test_down_cleans_up_a_recorded_but_already_dead_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir(parents=True)
            state = {
                "processes": {"worker": {"pid": 999999999, "log": str(run_dir / "worker.log")}},
                "postgres": {"started_by_alpha": False},
            }
            (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
            result = self._run_alpha("down", "--run-dir", str(run_dir))
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("already stopped", result.stdout)
        self.assertIn("did not start it", result.stdout)
        self.assertIn("alpha: down.", result.stdout)

    def test_logs_is_safe_when_nothing_is_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            result = self._run_alpha("logs", "--run-dir", str(run_dir))
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("nothing to show", result.stdout)

    def test_status_reports_a_non_default_recorded_port_without_repeating_the_flag(self):
        """Once `up` has recorded a non-default --web-port in the state file,
        `status` must report that real port from a fresh shell -- without
        --web-port being passed to `status` at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir(parents=True)
            env_file = Path(tmp) / "no_such_alpha.env"
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                state = {
                    "processes": {
                        "web": {"pid": proc.pid, "log": str(run_dir / "web.log"), "port": 3005},
                    },
                    "postgres": {"started_by_alpha": False},
                }
                (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
                # Deliberately no --web-port here: status must read the port
                # back from the state file, not require the flag again.
                result = self._run_alpha("status", "--run-dir", str(run_dir), "--env-file", str(env_file))
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("port 3005", result.stdout)


class _FakePopen:
    """Stands in for subprocess.Popen in TestFailedUpLeavesStateForDown --
    cmd_up only ever touches .pid and .poll()/.returncode on what _spawn
    returns, so a real process is unnecessary for exercising the
    persist-state-on-failed-rollback branch in isolation.
    """

    _next_pid = 424242

    def __init__(self):
        _FakePopen._next_pid += 1
        self.pid = _FakePopen._next_pid
        self.returncode = None

    def poll(self):
        return None


def _free_port() -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    return port


class TestFailedUpLeavesStateForDown(unittest.TestCase):
    """Regression coverage for the second orphan defect: a failed `up`
    previously cleared out/alpha_run/state.json unconditionally during
    rollback, so if rollback itself could not confirm everything had
    actually stopped, a later `down` had nothing left to find the survivor
    with ("no session recorded ... nothing to stop") even though something
    was still running. cmd_up must keep the state file whenever rollback
    could not confirm success, and only clear it when rollback is confirmed.

    Runs entirely against mocked internals (_ensure_postgres,
    _run_alembic_upgrade, _spawn, _wait_process_alive, _wait_for_port,
    _stop_processes, _stop_postgres) -- no real PostgreSQL, npm, or API
    process -- both per this module's "do not start the real web or API in
    unit tests" rule and because the behaviour under test is entirely
    about cmd_up's own state-file bookkeeping on the failure path.
    """

    def test_state_file_is_kept_not_cleared_when_rollback_cannot_confirm_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_file = Path(tmp) / "alpha.env"
            env_file.write_text(
                "OPPORTUNITYOS_FOUNDER_PASSWORD=hunter2\n"
                "OPPORTUNITYOS_SESSION_SECRET=abc123\n"
                "OPPORTUNITYOS_DB_URL=postgresql+psycopg2://u:p@127.0.0.1:5432/db\n",
                encoding="utf-8",
            )
            api_port = _free_port()

            with mock.patch.object(alpha, "_ensure_postgres", return_value={"started_by_alpha": False}), \
                 mock.patch.object(alpha, "_run_alembic_upgrade", return_value=None), \
                 mock.patch.object(alpha, "_spawn", side_effect=lambda *a, **k: _FakePopen()), \
                 mock.patch.object(alpha, "_wait_process_alive", return_value=None), \
                 mock.patch.object(
                     alpha, "_wait_for_port", side_effect=alpha.AlphaError("simulated: API never became healthy")
                 ), \
                 mock.patch.object(
                     alpha, "_stop_processes", return_value=(["mocked: rollback could not confirm"], False)
                 ) as stop_processes_mock, \
                 mock.patch.object(
                     alpha, "_stop_postgres", return_value=("mocked: postgres left running", True)
                 ):
                exit_code = alpha.cmd_up(env_file, run_dir, web_port=_free_port(), api_port=api_port)

            self.assertEqual(exit_code, 1)
            stop_processes_mock.assert_called_once()

            # The whole point: state must still be there for `down` to act on.
            state = alpha._load_state(run_dir)
            self.assertIn("processes", state)
            self.assertIn("worker", state["processes"])
            self.assertIn("api", state["processes"])

            # And `down`, run fresh afterwards, must be able to see it --
            # not report "no session recorded ... nothing to stop" the way
            # the reported defect did.
            with mock.patch.object(alpha, "_stop_processes", return_value=([], True)), \
                 mock.patch.object(alpha, "_stop_postgres", return_value=("stopped", True)):
                down_exit_code = alpha.cmd_down(run_dir)
            self.assertEqual(down_exit_code, 0)
            self.assertEqual(alpha._load_state(run_dir), {})

    def test_state_file_is_cleared_when_rollback_confirms_success(self):
        """The mirror-image case: when rollback genuinely confirms
        everything stopped, the state file should still be cleared (no
        change from the previous, correct behaviour for the clean case).
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_file = Path(tmp) / "alpha.env"
            env_file.write_text(
                "OPPORTUNITYOS_FOUNDER_PASSWORD=hunter2\n"
                "OPPORTUNITYOS_SESSION_SECRET=abc123\n"
                "OPPORTUNITYOS_DB_URL=postgresql+psycopg2://u:p@127.0.0.1:5432/db\n",
                encoding="utf-8",
            )
            api_port = _free_port()

            with mock.patch.object(alpha, "_ensure_postgres", return_value={"started_by_alpha": False}), \
                 mock.patch.object(alpha, "_run_alembic_upgrade", return_value=None), \
                 mock.patch.object(alpha, "_spawn", side_effect=lambda *a, **k: _FakePopen()), \
                 mock.patch.object(alpha, "_wait_process_alive", return_value=None), \
                 mock.patch.object(
                     alpha, "_wait_for_port", side_effect=alpha.AlphaError("simulated: API never became healthy")
                 ), \
                 mock.patch.object(
                     alpha, "_stop_processes", return_value=(["mocked: rollback confirmed"], True)
                 ), \
                 mock.patch.object(
                     alpha, "_stop_postgres", return_value=("mocked: postgres left running", True)
                 ):
                exit_code = alpha.cmd_up(env_file, run_dir, web_port=_free_port(), api_port=api_port)

            self.assertEqual(exit_code, 1)
            self.assertEqual(alpha._load_state(run_dir), {})


if __name__ == "__main__":
    unittest.main()
