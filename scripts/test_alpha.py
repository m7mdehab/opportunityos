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
        message = alpha._stop_postgres({"started_by_alpha": False})
        self.assertIn("did not start it", message)

    def test_stop_postgres_calls_pg_ctl_stop_when_alpha_started_it(self):
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            message = alpha._stop_postgres(
                {"started_by_alpha": True, "pg_ctl": "pg_ctl.exe", "data_dir": "D:/data"}
            )
        self.assertIn("stopped", message)
        run_mock.assert_called_once()
        called_cmd = run_mock.call_args[0][0]
        self.assertIn("stop", called_cmd)
        self.assertIn("D:/data", called_cmd)


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


if __name__ == "__main__":
    unittest.main()
