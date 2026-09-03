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

import contextlib
import inspect
import io
import json
import os
import re
import secrets
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
import storage.engine as storage_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
ALPHA_SCRIPT = REPO_ROOT / "scripts" / "alpha.py"


def _synthetic_value(prefix: str, entropy_bytes: int) -> str:
    """Build a throwaway test value that is generated, never hard-coded --
    see api/test_api.py's own helper of the same shape. A literal assigned
    to a name like PASSWORD or SECRET is exactly what scripts/check_guard.py
    rejects; generating instead of hard-coding also means the value differs
    every run, so it cannot be copied into anything real by accident.
    Nothing here is a credential.
    """
    return prefix + secrets.token_urlsafe(entropy_bytes)


@contextlib.contextmanager
def _listening_on(port: int):
    """Bind and actively accept-and-drop connections on 127.0.0.1:``port``
    for the duration of the with-block -- stands in for the real web dev
    server actually being reachable, which _wait_web_ready's TCP
    confirmation check (added after the "ready line printed, then Next
    detected another dev server and exited" defect) now requires before
    reporting success. A bare listen() backlog with nothing calling
    accept() only answers the very first connect attempt and then refuses
    the rest (see TestStopProcessesPortVerification's own note on this) --
    not representative of a real listening server, and not what
    _wait_web_ready polls with repeatedly -- so this accepts (and
    immediately drops) connections in a loop for as long as the block runs.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    srv.settimeout(0.2)
    stop_accepting = threading.Event()

    def _accept_loop():
        while not stop_accepting.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            conn.close()

    thread = threading.Thread(target=_accept_loop, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_accepting.set()
        thread.join(timeout=5)
        srv.close()


def _free_port() -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    return port


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

    # -- unedited placeholder detection ------------------------------------------

    def test_unedited_template_copy_is_rejected_naming_every_placeholder_key(self):
        """The most common first mistake: copy the shipped template to
        private/alpha.env and forget to edit it. Every key is present (so
        the missing-key check alone would say nothing is wrong), but every
        value is still REPLACE_WITH_* -- this must be caught here, by name,
        rather than surfacing later as a raw SQLAlchemy/psycopg2 traceback
        out of `alembic upgrade head`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            # A real, unedited copy of the shipped template -- not a
            # hand-written fixture -- so this test tracks the actual
            # template's placeholder wording.
            env_path.write_text(alpha.ENV_TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha.load_alpha_env(env_path)
            message = str(ctx.exception)
            self.assertIn(str(env_path), message)
            self.assertIn("placeholders", message)
            self.assertIn("OPPORTUNITYOS_FOUNDER_PASSWORD", message)
            self.assertIn("OPPORTUNITYOS_SESSION_SECRET", message)
            self.assertIn("OPPORTUNITYOS_DB_URL", message)

    def test_partially_edited_template_names_only_the_still_unedited_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text(
                "OPPORTUNITYOS_FOUNDER_PASSWORD=a-real-password\n"
                "OPPORTUNITYOS_SESSION_SECRET=REPLACE_WITH_A_RANDOM_SESSION_SECRET\n"
                "OPPORTUNITYOS_DB_URL=postgresql+psycopg2://REPLACE_WITH_DB_USER:REPLACE_WITH_DB_PASSWORD"
                "@127.0.0.1:5432/REPLACE_WITH_DB_NAME\n",
                encoding="utf-8",
            )
            with self.assertRaises(alpha.AlphaError) as ctx:
                alpha.load_alpha_env(env_path)
            message = str(ctx.exception)
            self.assertNotIn("OPPORTUNITYOS_FOUNDER_PASSWORD", message)
            self.assertIn("OPPORTUNITYOS_SESSION_SECRET", message)
            self.assertIn("OPPORTUNITYOS_DB_URL", message)

    def test_fully_edited_values_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text(
                "OPPORTUNITYOS_FOUNDER_PASSWORD=a-real-password\n"
                "OPPORTUNITYOS_SESSION_SECRET=a-real-session-secret\n"
                "OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos:pw@127.0.0.1:5432/oos\n",
                encoding="utf-8",
            )
            values = alpha.load_alpha_env(env_path)  # must not raise
            self.assertEqual(values["OPPORTUNITYOS_FOUNDER_PASSWORD"], "a-real-password")


class TestUpRejectsAnUneditedTemplate(unittest.TestCase):
    """`up` must reject an unedited private/alpha.env before it ever touches
    PostgreSQL detection, migrations, or spawns anything -- not partway
    through, and not by letting `alembic upgrade head` fail first with an
    opaque connection traceback.
    """

    def test_nothing_is_started_when_the_template_is_unedited(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_path = Path(tmp) / "alpha.env"
            env_path.write_text(alpha.ENV_TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            with mock.patch.object(alpha, "_ensure_postgres") as ensure_postgres_mock, \
                 mock.patch.object(alpha, "_run_alembic_upgrade") as alembic_mock, \
                 mock.patch.object(alpha, "_spawn") as spawn_mock:
                exit_code = alpha.cmd_up(env_path, run_dir)

            self.assertEqual(exit_code, 1)
            ensure_postgres_mock.assert_not_called()
            alembic_mock.assert_not_called()
            spawn_mock.assert_not_called()
            # No partial run state should exist either -- this failure
            # happens before anything is tracked.
            self.assertEqual(alpha._load_state(run_dir), {})


class TestExtractDbName(unittest.TestCase):
    """`_extract_db_name` must handle every URL shape this project actually
    produces: with/without a password, with/without a trailing query string.
    """

    def test_with_password_no_query_string(self):
        self.assertEqual(
            alpha._extract_db_name("postgresql+psycopg2://user:pw@127.0.0.1:5432/opportunityos_alpha"),
            "opportunityos_alpha",
        )

    def test_without_password_no_query_string(self):
        self.assertEqual(
            alpha._extract_db_name("postgresql+psycopg2://user@127.0.0.1:5432/opportunityos_alpha"),
            "opportunityos_alpha",
        )

    def test_with_password_and_query_string(self):
        self.assertEqual(
            alpha._extract_db_name(
                "postgresql+psycopg2://user:pw@127.0.0.1:5432/opportunityos_test?sslmode=disable"
            ),
            "opportunityos_test",
        )

    def test_without_password_and_with_query_string(self):
        self.assertEqual(
            alpha._extract_db_name(
                "postgresql+psycopg2://user@127.0.0.1:5432/opportunityos_test?sslmode=disable"
            ),
            "opportunityos_test",
        )

    def test_missing_database_name_raises_a_clear_error(self):
        with self.assertRaises(alpha.AlphaError) as ctx:
            alpha._extract_db_name("postgresql+psycopg2://user@127.0.0.1:5432/")
        self.assertIn("no database name", str(ctx.exception))


class TestRefuseTestDatabase(unittest.TestCase):
    """`_refuse_test_database` -- the function `cmd_up` calls before any
    PostgreSQL detection or migration -- must reject any database name
    ending `_test`, name that database in its message, and must not be
    fooled by a trailing query string. A name that merely contains, but
    does not end in, `_test` (e.g. `opportunityos_testing`) must be
    accepted -- only an exact suffix match refuses.
    """

    def test_test_suffixed_name_is_refused_and_named_in_the_message(self):
        with self.assertRaises(alpha.AlphaError) as ctx:
            alpha._refuse_test_database(
                "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test"
            )
        message = str(ctx.exception)
        self.assertIn("opportunityos_test", message)
        self.assertIn("_test", message)

    def test_test_suffixed_name_with_query_parameters_is_still_refused(self):
        """The parser must not be fooled by `...(/opportunityos_test?sslmode=disable)`."""
        with self.assertRaises(alpha.AlphaError) as ctx:
            alpha._refuse_test_database(
                "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test?sslmode=disable"
            )
        self.assertIn("opportunityos_test", str(ctx.exception))

    def test_opportunityos_alpha_name_is_accepted(self):
        alpha._refuse_test_database(
            "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_alpha"
        )  # must not raise

    def test_a_name_merely_containing_test_but_not_ending_in_it_is_accepted(self):
        alpha._refuse_test_database(
            "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_testing"
        )  # must not raise -- only an exact "_test" suffix refuses


class TestUpRejectsATestDatabase(unittest.TestCase):
    """`up` must refuse a database name ending in `_test` before ever
    touching PostgreSQL detection or migrations -- mirrors
    TestUpRejectsAnUneditedTemplate's own proof technique (mocking
    `_ensure_postgres`/`_run_alembic_upgrade`/`_spawn` and asserting none of
    them are called) so this is a placement proof, not merely an outcome
    proof, and covers both a plain `_test` name and one with a trailing
    query string.
    """

    def _env_file(self, tmp: str, db_url: str) -> Path:
        env_path = Path(tmp) / "alpha.env"
        env_path.write_text(
            f"OPPORTUNITYOS_FOUNDER_PASSWORD={_synthetic_value('pw-', 12)}\n"
            f"OPPORTUNITYOS_SESSION_SECRET={_synthetic_value('sig-', 24)}\n"
            f"OPPORTUNITYOS_DB_URL={db_url}\n",
            encoding="utf-8",
        )
        return env_path

    def _assert_refused(self, db_url: str, expected_db_name: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_path = self._env_file(tmp, db_url)
            stderr = io.StringIO()
            with mock.patch.object(alpha, "_ensure_postgres") as ensure_postgres_mock, \
                 mock.patch.object(alpha, "_run_alembic_upgrade") as alembic_mock, \
                 mock.patch.object(alpha, "_spawn") as spawn_mock, \
                 contextlib.redirect_stderr(stderr):
                exit_code = alpha.cmd_up(env_path, run_dir)

            self.assertEqual(exit_code, 1)
            ensure_postgres_mock.assert_not_called()
            alembic_mock.assert_not_called()
            spawn_mock.assert_not_called()
            self.assertIn(expected_db_name, stderr.getvalue())
            # No partial run state either -- this failure happens before
            # anything is tracked, same as the unedited-template case above.
            self.assertEqual(alpha._load_state(run_dir), {})

    def test_plain_test_database_name_is_refused_naming_the_database(self):
        self._assert_refused(
            "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test",
            "opportunityos_test",
        )

    def test_test_database_with_query_parameters_is_still_refused_and_not_fooled_by_them(self):
        self._assert_refused(
            "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test?sslmode=disable",
            "opportunityos_test",
        )


class TestStatusRefusesATestDatabase(unittest.TestCase):
    """`status` must refuse a database name ending in `_test` too -- not
    just `up`. Regression coverage for the Master's own re-run finding:
    `status --env-file <env naming opportunityos_test>` previously exited 0
    and (against a properly migrated opportunityos_test -- the normal state,
    since that is the suite's own database) would have printed that
    database's poll history to the founder as though it were their own,
    the exact FR-004 defect in milder form. The refusal is enforced inside
    `load_alpha_env` itself (see `AlphaTestDatabaseRefusalError`'s own
    docstring), so this is regression coverage for that shared code path
    from `status`'s own call site, not a re-test of `_refuse_test_database`
    itself (already covered by TestRefuseTestDatabase).
    """

    def _env_file(self, tmp: str, db_url: str) -> Path:
        env_path = Path(tmp) / "alpha.env"
        env_path.write_text(
            f"OPPORTUNITYOS_FOUNDER_PASSWORD={_synthetic_value('pw-', 12)}\n"
            f"OPPORTUNITYOS_SESSION_SECRET={_synthetic_value('sig-', 24)}\n"
            f"OPPORTUNITYOS_DB_URL={db_url}\n",
            encoding="utf-8",
        )
        return env_path

    def test_status_refuses_and_exits_nonzero_naming_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_path = self._env_file(
                tmp, "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = alpha.cmd_status(env_path, run_dir)

        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("opportunityos_test", output)
        self.assertIn("refused", output)
        # Never falls through to the generic "could not query the database"
        # degrade path below the refusal -- that would mean a connection
        # was actually attempted.
        self.assertNotIn("could not query the database", output)

    def test_status_with_a_query_string_test_database_is_still_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_path = self._env_file(
                tmp,
                "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test?sslmode=disable",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = alpha.cmd_status(env_path, run_dir)

        self.assertEqual(exit_code, 1)
        self.assertIn("opportunityos_test", stdout.getvalue())

    def test_status_never_calls_get_engine_when_the_database_is_refused(self):
        """Placement proof, mirroring TestUpRejectsATestDatabase's own
        technique: `storage.engine.get_engine` is the only thing in
        `cmd_status` that ever opens a database connection (see
        cmd_status's own `from storage.engine import get_engine, ...`,
        executed only after the refusal check). Mocking the attribute on
        the real module `cmd_status` imports from and asserting it was
        never called is direct proof no connection was ever attempted --
        stronger than checking output alone.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_path = self._env_file(
                tmp, "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test"
            )
            with mock.patch.object(storage_engine, "get_engine") as get_engine_mock, \
                 contextlib.redirect_stdout(io.StringIO()):
                exit_code = alpha.cmd_status(env_path, run_dir)

        self.assertEqual(exit_code, 1)
        get_engine_mock.assert_not_called()

    def test_status_on_an_opportunityos_alpha_database_is_not_refused(self):
        """The accepted name must not be refused either -- status then
        proceeds to (and fails gracefully within) the real DB-query
        section, since nothing is actually listening at this fake
        host/port in this test; the point here is only that it is not
        refused before that.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            # Port 1 is a reserved, never-listening port, so the DB-query
            # section fails fast with a connection error rather than
            # hanging -- this test is only about the refusal *not* firing,
            # not about a real database.
            env_path = self._env_file(
                tmp, "postgresql+psycopg2://opportunityos@127.0.0.1:1/opportunityos_alpha"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = alpha.cmd_status(env_path, run_dir)

        # Exit 0 either way (status degrades gracefully on a real connection
        # failure) -- what matters is the message is the generic
        # "unavailable: could not query the database", not this module's
        # own "(refused: ...)" line. (Not a bare `assertNotIn("refused", ...)`
        # -- psycopg2's own OperationalError text contains "Connection
        # refused", which would make that a false positive here.)
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("could not query the database", output)
        self.assertNotIn("(refused:", output)


class TestDownAndLogsNeverResolveTheDatabaseUrl(unittest.TestCase):
    """`down` and `logs` are deliberately exempt from the `_test` refusal --
    not silently, but because they never call `load_alpha_env` (and so
    never resolve OPPORTUNITYOS_DB_URL) at all: both act purely on the
    run-dir state file recording what `up` itself already started. A stray
    previous session must still be stoppable (or its logs still readable)
    even if the founder's env file currently names a test database --
    refusing here would actively prevent cleanup rather than protect
    anything. This is an executable version of that argument: their own
    signatures take no `env_file` parameter, so a future change that made
    them start resolving OPPORTUNITYOS_DB_URL would show up here as a
    parameter-list change, not silently.
    """

    def test_cmd_down_takes_no_env_file_parameter(self):
        self.assertNotIn("env_file", inspect.signature(alpha.cmd_down).parameters)

    def test_cmd_logs_takes_no_env_file_parameter(self):
        self.assertNotIn("env_file", inspect.signature(alpha.cmd_logs).parameters)


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
        # A real listener on the expected port -- success requires not just
        # a matching ready line but a genuine, still-answering TCP endpoint
        # (see the "ready line printed, then exited" defect this class also
        # covers further down).
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  ▲ Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{port}\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                with _listening_on(port):
                    # Must not raise.
                    alpha._wait_web_ready(proc, log_path, expected_port=port, timeout_seconds=5)
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
        """`--web-port` must be verified exactly like the default: a child
        reporting the requested (non-default) port in its own ready line,
        and genuinely reachable there, must be accepted.
        """
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{port}\n",
                encoding="utf-8",
            )
            proc = self._spawn_long_lived()
            try:
                with _listening_on(port):
                    # Must not raise.
                    alpha._wait_web_ready(proc, log_path, expected_port=port, timeout_seconds=5)
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

        The "stale" port below (a fixed, deliberately never-dialed number)
        is never actually bound by this test -- it only ever appears as
        text in the log, exactly like a real prior run's ready line would
        be. Only the real, current-run port is a genuine free port obtained
        dynamically, and only that one is ever listened on.
        """
        stale_port = 39501  # never dialed -- see docstring
        real_port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            # A previous, unrelated `up` attempt's own ready line.
            log_path.write_text(
                "  Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{stale_port}\n",
                encoding="utf-8",
            )
            log_offset = log_path.stat().st_size  # recorded "immediately before this spawn"
            # This run's own line, appended after the offset was captured --
            # exactly what _spawn's append-mode open produces in practice.
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("  Next.js 16.3.4\n")
                handle.write(f"  - Local:         http://localhost:{real_port}\n")

            proc = self._spawn_long_lived()
            try:
                with _listening_on(real_port):
                    # Must not raise: real_port (after the offset) matches
                    # what was requested and is genuinely reachable; the
                    # stale line (before the offset) must never be
                    # considered.
                    alpha._wait_web_ready(
                        proc, log_path, expected_port=real_port, timeout_seconds=5, log_offset=log_offset
                    )
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_without_the_offset_the_stale_line_causes_a_false_failure(self):
        """Documents the defect directly: the same log/ports as the test
        above, but called without log_offset (today's default, 0) -- the
        stale line wins and a perfectly successful bind is reported as a
        mismatch. Never dials either port (the mismatch is raised before
        any liveness check), so neither needs to be a genuinely free port.
        """
        stale_port = 39501
        real_port = 39502
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{stale_port}\n",
                encoding="utf-8",
            )
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("  Next.js 16.3.4\n")
                handle.write(f"  - Local:         http://localhost:{real_port}\n")

            proc = self._spawn_long_lived()
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=real_port, timeout_seconds=5)
                self.assertIn(str(stale_port), str(ctx.exception))
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    # -- ready line is not proof by itself (Next's "another dev server" lock) ---

    def test_a_correct_ready_line_followed_by_exit_is_treated_as_a_failure(self):
        """The exact real-world defect this class was extended for: Next
        can print a fully correct "- Local:" ready line for the requested
        port, then -- moments later -- notice a pre-existing dev server for
        the same project directory and exit, having never actually served
        anything. Matching the ready line text is not proof by itself; this
        must be reported as a failure, not success. A test that would fail
        against the pre-fix behaviour, which returned as soon as the ready
        line matched, without ever checking the process was still alive or
        the port still answering.
        """
        port = _free_port()  # deliberately never listened on: nothing should ever accept here
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{port}\n"
                "  Ready in 4.4s\n",
                encoding="utf-8",
            )
            # Exits shortly after the ready line was already written --
            # mirrors Next printing "ready", then noticing the lock, then
            # exiting a moment later.
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=port, timeout_seconds=5)
                message = str(ctx.exception)
                self.assertIn("reported it was ready", message)
                self.assertIn(str(port), message)
                self.assertIn("exited", message)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)

    def test_names_the_existing_pid_and_port_when_another_dev_server_holds_the_lock(self):
        """Next has already diagnosed this precisely -- surface it verbatim
        (naming the *existing* server's pid and port, not this run's)
        instead of a generic "the child exited".
        """
        this_run_port = _free_port()  # never listened on -- the point is this run's own bind is moot
        existing_port = 3210
        existing_pid = 21856
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "web.log"
            log_path.write_text(
                "  Next.js 16.3.4\n"
                f"  - Local:         http://localhost:{this_run_port}\n"
                "  Ready in 4.4s\n"
                "  Another next dev server is already running.\n"
                f"  - Local:         http://localhost:{existing_port}\n"
                f"  - PID:           {existing_pid}\n",
                encoding="utf-8",
            )
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
            try:
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._wait_web_ready(proc, log_path, expected_port=this_run_port, timeout_seconds=5)
                message = str(ctx.exception)
                self.assertIn("already running", message)
                self.assertIn(str(existing_pid), message)
                self.assertIn(str(existing_port), message)
                self.assertIn("--web-port", message)
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
        # Spawned via alpha._spawn -- not a bare subprocess.Popen -- because
        # that is the only thing _kill_pid_tree is ever safe to call on: on
        # POSIX it signals the process *group* (os.killpg), which is only
        # correct because _spawn starts every child with
        # start_new_session=True (its own new group, pgid == its own pid).
        # A bare subprocess.Popen here would share *this test runner's own*
        # process group, so os.killpg would signal the test runner itself.
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "standin.log"
            proc = alpha._spawn(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                Path(tempfile.gettempdir()),
                os.environ.copy(),
                log_path,
            )
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

    def test_kill_pid_tree_kills_the_whole_tree_not_just_the_tracked_pid(self):
        """Regression coverage for the actual defect (not merely the
        zombie-reporting symptom the CI assertion caught): on POSIX, a bare
        ``os.kill(pid, SIGTERM)`` (the previous behaviour) only ever
        signalled the one tracked pid, never anything *that* pid had itself
        spawned -- exactly what npm -> Next -> Next's own dev-server child
        looks like. This spawns via ``alpha._spawn`` (the same call
        ``cmd_up`` itself uses) so the POSIX branch's
        ``start_new_session=True`` is exercised precisely as in production,
        then confirms ``_kill_pid_tree`` takes down a grandchild the
        tracked pid spawned on its own, not merely the tracked pid --
        fails against the pre-fix ``os.kill(pid, SIGTERM)``-only POSIX
        implementation, which left the grandchild running.
        """
        grandchild_pid = None
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "tree.log"
            child_script = (
                "import subprocess, sys, time\n"
                "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "print(gc.pid, flush=True)\n"
                "time.sleep(60)\n"
            )
            proc = alpha._spawn(
                [sys.executable, "-c", child_script],
                Path(tempfile.gettempdir()),
                os.environ.copy(),
                log_path,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and grandchild_pid is None:
                    if log_path.exists():
                        content = log_path.read_text(encoding="utf-8").strip()
                        if content:
                            grandchild_pid = int(content.splitlines()[0])
                    time.sleep(0.2)
                self.assertIsNotNone(
                    grandchild_pid, "the stand-in child never reported its own grandchild's pid"
                )

                self.assertTrue(alpha._pid_alive(proc.pid))
                self.assertTrue(alpha._pid_alive(grandchild_pid))

                alpha._kill_pid_tree(proc.pid)

                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and (
                    alpha._pid_alive(proc.pid) or alpha._pid_alive(grandchild_pid)
                ):
                    time.sleep(0.2)

                self.assertFalse(alpha._pid_alive(proc.pid), "the tracked pid should be gone")
                self.assertFalse(
                    alpha._pid_alive(grandchild_pid),
                    "the grandchild should be gone too -- this is the actual regression",
                )
            finally:
                for leftover_pid in (proc.pid, grandchild_pid):
                    if leftover_pid is None or not alpha._pid_alive(leftover_pid):
                        continue
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(leftover_pid), "/F"], capture_output=True
                        )
                    else:
                        try:
                            os.kill(leftover_pid, 9)
                        except OSError:
                            pass
                # _kill_pid_tree operates on raw pids (os.killpg/taskkill),
                # never on this Popen object itself, so its own returncode
                # is never updated as a side effect -- reap it explicitly
                # here so the Popen object is not garbage-collected with
                # returncode still None (a ResourceWarning, not a failure,
                # but avoidable).
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

    @unittest.skipIf(os.name == "nt", "zombie process state is POSIX-specific; Windows has no equivalent")
    def test_is_zombie_detects_an_unreaped_exited_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])  # exits almost immediately
        try:
            deadline = time.monotonic() + 5
            became_zombie = False
            while time.monotonic() < deadline:
                if alpha._is_zombie(proc.pid):
                    became_zombie = True
                    break
                time.sleep(0.1)
            self.assertTrue(became_zombie, "the stand-in process never became a zombie in time")
        finally:
            proc.wait(timeout=5)  # actually reap it, so this test leaves nothing behind

    @unittest.skipIf(os.name == "nt", "zombie process state is POSIX-specific; Windows has no equivalent")
    def test_pid_alive_treats_an_unreaped_zombie_as_not_alive(self):
        """Problem 2 directly: ``os.kill(pid, 0)`` succeeds for a zombie
        (exited, not yet reaped) exactly as it does for a live process --
        without this fix, ``_pid_alive`` would report a process this module
        itself just killed (see ``_kill_pid_tree``) as still alive, which
        is exactly what the reported CI failure on Linux caught. Fails
        against the pre-fix ``_pid_alive``, which was a bare
        ``os.kill(pid, 0)`` with no reaping or zombie check at all.
        """
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not alpha._is_zombie(proc.pid):
                time.sleep(0.1)
            self.assertFalse(alpha._pid_alive(proc.pid))
        finally:
            proc.wait(timeout=5)


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
    _DB_URL = "postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_alpha"

    def test_already_listening_is_detected_and_not_restarted(self):
        with mock.patch.object(alpha, "_port_open", return_value=True), \
             mock.patch.object(alpha, "_ensure_database_exists") as ensure_db_mock:
            result = alpha._ensure_postgres(Path(tempfile.gettempdir()), self._DB_URL)
        self.assertEqual(result, {"started_by_alpha": False, "database": "opportunityos_alpha"})
        ensure_db_mock.assert_called_once_with(self._DB_URL)

    def test_missing_localappdata_raises_a_clear_error(self):
        env_without_localappdata = {k: v for k, v in os.environ.items() if k != "LOCALAPPDATA"}
        with mock.patch.object(alpha, "_port_open", return_value=False):
            with mock.patch.dict(os.environ, env_without_localappdata, clear=True):
                with self.assertRaises(alpha.AlphaError) as ctx:
                    alpha._ensure_postgres(Path(tempfile.gettempdir()), self._DB_URL)
        self.assertIn("LOCALAPPDATA", str(ctx.exception))

    def test_missing_portable_cluster_raises_a_clear_error_naming_the_brief(self):
        with tempfile.TemporaryDirectory() as fake_localappdata:
            with mock.patch.object(alpha, "_port_open", return_value=False):
                with mock.patch.dict(os.environ, {"LOCALAPPDATA": fake_localappdata}):
                    with self.assertRaises(alpha.AlphaError) as ctx:
                        alpha._ensure_postgres(Path(tempfile.gettempdir()), self._DB_URL)
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

    def test_status_exits_nonzero_against_a_test_database_as_a_real_subprocess(self):
        """Regression test for the Master's own re-run finding: reproduces
        the exact repro steps reported (`status --env-file <env naming
        opportunityos_test>`), as a real subprocess exactly like the
        Master ran it -- not just via a direct `cmd_status` call.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            env_file = Path(tmp) / "alpha.env"
            env_file.write_text(
                f"OPPORTUNITYOS_FOUNDER_PASSWORD={_synthetic_value('pw-', 12)}\n"
                f"OPPORTUNITYOS_SESSION_SECRET={_synthetic_value('sig-', 24)}\n"
                "OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test\n",
                encoding="utf-8",
            )
            result = self._run_alpha("status", "--run-dir", str(run_dir), "--env-file", str(env_file))
        self.assertNotEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertIn("opportunityos_test", result.stdout)
        self.assertNotIn("could not query the database", result.stdout)

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

            with mock.patch.object(
                     alpha, "_ensure_postgres", return_value={"started_by_alpha": False, "database": "db"}
                 ), \
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

            with mock.patch.object(
                     alpha, "_ensure_postgres", return_value={"started_by_alpha": False, "database": "db"}
                 ), \
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


class TestPersistBatchProducesRealSourceIds(unittest.TestCase):
    """Integration: `persist_batch` from a real adapter + a real, already-
    committed fixture file produces `OpportunityRecord` rows carrying the
    adapter's own real per-job ids -- never the synthetic `src-1`/
    `opp-uq-*` shape the FR-004 erratum (reports/REPORT-FR-004.md) records
    `alpha.py up` once serving to the founder as though it were real polled
    data. No live network I/O: the payload is read from
    opportunity/fixtures/greenhouse_cloudflare.json (already committed) and
    parsed by the real GreenhouseAdapter, exactly as opportunity/test_adapters.py
    does.

    Requires a real PostgreSQL OPPORTUNITYOS_DB_URL, same requirement and
    skip/fail-loud behaviour as storage/test_postgres_integration.py.
    """

    @classmethod
    def setUpClass(cls):
        cls.db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if not cls.db_url or not cls.db_url.startswith("postgresql"):
            if os.environ.get("CI"):
                raise AssertionError(
                    "CI is set but OPPORTUNITYOS_DB_URL is missing or not a PostgreSQL URL "
                    f"(postgresql+psycopg2://...). Got: {cls.db_url!r}."
                )
            raise unittest.SkipTest(
                f"requires a real PostgreSQL OPPORTUNITYOS_DB_URL, got: {cls.db_url!r}"
            )

        from alembic import command
        from alembic.config import Config
        from storage.engine import get_engine, get_session_factory
        from storage.models import Base

        cls.engine = get_engine(cls.db_url)
        cls.SessionFactory = get_session_factory(cls.engine)
        cls.Base = Base

        alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", cls.db_url)
        command.upgrade(alembic_cfg, "head")

    def setUp(self):
        from sqlalchemy import text

        with self.engine.begin() as conn:
            for table in reversed(self.Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))

    def test_persist_batch_from_a_real_greenhouse_fixture_is_not_synthetic(self):
        from opportunity.adapters.greenhouse import GreenhouseAdapter
        from opportunity.persistence import persist_batch
        from opportunity.pipeline import IngestionBatch
        from opportunity.registry import SourceRegistry
        from storage.models import OpportunityRecord
        from storage.repository import StorageRepository

        fixture_path = REPO_ROOT / "opportunity" / "fixtures" / "greenhouse_cloudflare.json"
        payload = fixture_path.read_text(encoding="utf-8")

        adapter = GreenhouseAdapter("cloudflare")
        parse_result = adapter.parse_payload(
            payload, raw_pointer="fixture:greenhouse", fetched_at="2026-08-30"
        )
        self.assertEqual(len(parse_result.opportunities), 2)

        # The adapter's own source id ("greenhouse:cloudflare") must itself
        # be one docs/SOURCE_REGISTRY.yaml actually recognizes -- proving
        # this is a real, policy-governed source, not a fabricated
        # placeholder like FR-004's "src-1".
        registry = SourceRegistry()
        self.assertTrue(registry.is_source_registered(adapter.source_id))
        self.assertEqual(adapter.source_id, "greenhouse:cloudflare")

        batch = IngestionBatch(
            batch_id="fixture-batch",
            run_id="fixture-run",
            ingested_at="2026-08-30",
            opportunities=parse_result.opportunities,
            clusters=(),
            health_reports=(),
            total_raw_ingested=parse_result.records_raw_count,
            total_unique_opportunities=len(parse_result.opportunities),
            exact_duplicates_removed=0,
            cross_source_duplicates_clustered=0,
            ambiguous_duplicates_count=0,
            track_counts=(),
            eligibility_counts=(),
        )

        session = self.SessionFactory()
        try:
            repository = StorageRepository(session)
            result = persist_batch(batch, repository)
        finally:
            session.close()

        self.assertEqual(result.inserted_count, 2)

        session = self.SessionFactory()
        try:
            rows = session.query(OpportunityRecord).order_by(OpportunityRecord.id).all()
        finally:
            session.close()

        self.assertEqual(len(rows), 2)
        # The persisted row's source_id column carries the real, registered
        # source id ("greenhouse:cloudflare") -- never the synthetic
        # "src-1" FR-004's erratum recorded being served to the founder, and
        # never a bare per-job number (BRIEF-FR-005's own source_id erratum:
        # opportunity/persistence.py used to map opp.source_id -- the job's
        # remote id at Greenhouse, e.g. "5512301" -- onto this column
        # instead of opp.source, the registry id). The fixture's own real
        # Greenhouse job ids are preserved instead in each row's primary key
        # (see the id assertion below), not duplicated into source_id.
        row_source_ids = sorted(row.source_id for row in rows)
        self.assertEqual(row_source_ids, ["greenhouse:cloudflare", "greenhouse:cloudflare"])
        for row in rows:
            self.assertNotEqual(row.source_id, "src-1")
            self.assertNotIn("opp-uq-", row.id)
            self.assertTrue(row.id.startswith("greenhouse:cloudflare:"))


_PYTHON_ARGV0_RE = re.compile(r'\[\s*(["\'])python\1\s*,')


class TestNoPythonLiteralArgv0(unittest.TestCase):
    """scripts/dev_env.py work order F2, item 5 (the `sys.executable` sweep):
    every subprocess argv[0] that spawns a Python child process must be
    `sys.executable`, never the literal "python" -- bare `python` on this
    machine resolves to an older interpreter missing this project's
    dependencies (see scripts/dev_env.py's own docstring). A static source
    scan, not a mocked-subprocess assertion, so it also catches any future
    literal added anywhere in this file without needing to enumerate every
    call site by name.
    """

    def test_alpha_py_never_spawns_a_python_child_via_a_literal_argv0(self):
        source = (REPO_ROOT / "scripts" / "alpha.py").read_text(encoding="utf-8")
        match = _PYTHON_ARGV0_RE.search(source)
        self.assertIsNone(
            match,
            f"found a literal \"python\"/'python' as a subprocess argv[0] in scripts/alpha.py "
            f"near {match.group(0) if match else ''!r} -- use sys.executable instead.",
        )


if __name__ == "__main__":
    unittest.main()
