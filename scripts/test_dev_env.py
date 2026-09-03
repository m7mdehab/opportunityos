"""Tests for scripts/dev_env.py.

Anything that would otherwise touch PostgreSQL is mocked, except the slug
validation tests (which never reach PostgreSQL at all -- validation happens
first) and the drop-all exclusion test, which runs against this machine's
real local PostgreSQL (per this deliverable's own work order, F2-devenv.md,
Test DB: opportunityos_test_f2) and is skipped if that instance is not
reachable.
"""
from __future__ import annotations

import contextlib
import io
import socket
import unittest
from pathlib import Path
from unittest import mock

import scripts.dev_env as dev_env


def _postgres_reachable() -> bool:
    try:
        with socket.create_connection((dev_env.PG_HOST, dev_env.PG_PORT), timeout=1.0):
            return True
    except OSError:
        return False


class TestSlugValidation(unittest.TestCase):
    """`testdb <slug>` validates before ever touching PostgreSQL."""

    def test_rejects_a_slug_with_a_space_and_names_the_pattern(self):
        with self.assertRaises(SystemExit) as ctx:
            dev_env.cmd_testdb_create("Bad Slug")
        self.assertIn(dev_env.SLUG_PATTERN, str(ctx.exception))

    def test_rejects_uppercase(self):
        with self.assertRaises(SystemExit):
            dev_env.cmd_testdb_create("UpperCase")

    def test_rejects_a_slug_over_32_characters(self):
        with self.assertRaises(SystemExit):
            dev_env.cmd_testdb_create("a" * 33)

    def test_accepts_a_valid_slug_without_touching_postgres(self):
        with mock.patch.object(dev_env.alpha, "_ensure_database_exists") as ensure_mock:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = dev_env.cmd_testdb_create("f2probe")
        self.assertEqual(exit_code, 0)
        ensure_mock.assert_called_once_with("postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_f2probe")
        self.assertEqual(stdout.getvalue().strip().splitlines()[-1], ensure_mock.call_args[0][0])


class TestCheckHelpers(unittest.TestCase):
    def test_node_modules_check_fails_when_missing_and_names_the_fix(self):
        with tempdir_web(self) as web_dir:
            with mock.patch.object(dev_env, "WEB_DIR", web_dir):
                ok, detail = dev_env._check_node_modules()
        self.assertFalse(ok)
        self.assertIn("npm install", detail)

    def test_node_modules_check_passes_when_present(self):
        with tempdir_web(self) as web_dir:
            (web_dir / "node_modules").mkdir()
            with mock.patch.object(dev_env, "WEB_DIR", web_dir):
                ok, detail = dev_env._check_node_modules()
        self.assertTrue(ok)

    def test_pdf_renderer_check_reports_reportlab_and_never_mentions_libreoffice(self):
        ok, detail = dev_env._check_pdf_renderer()
        self.assertTrue(ok)
        self.assertIn("reportlab", detail)
        self.assertNotIn("LibreOffice", detail)
        self.assertNotIn("soffice", detail)

    def test_playwright_check_reports_fail_and_the_fix_when_the_probed_path_is_missing(self):
        fake_result = mock.Mock(
            returncode=0,
            stdout="Chrome for Testing 1.0 (playwright chromium v9999)\n"
            "  Install location:    C:\\definitely\\does\\not\\exist\\chromium-9999\n",
            stderr="",
        )
        with tempdir_web(self) as web_dir:
            (web_dir / "node_modules").mkdir()
            with mock.patch.object(dev_env, "WEB_DIR", web_dir), mock.patch(
                "subprocess.run", return_value=fake_result
            ):
                ok, detail = dev_env._check_playwright_browsers()
        self.assertFalse(ok)
        self.assertIn("npx playwright install chromium", detail)


class TestCmdUpRunsEveryCheck(unittest.TestCase):
    """`up` never stops at the first failure -- every check always runs, and
    the exit code reflects whether *any* check failed."""

    def test_all_checks_run_and_exit_is_nonzero_when_one_fails(self):
        calls: list[str] = []

        def _ok(name):
            def _check():
                calls.append(name)
                return True, f"{name} ok"

            return _check

        def _fail(name):
            def _check():
                calls.append(name)
                return False, f"{name} failed"

            return _check

        fake_checks = [
            ("first", _ok("first")),
            ("second-fails", _fail("second-fails")),
            ("third", _ok("third")),
        ]
        with mock.patch.object(dev_env, "_CHECKS", fake_checks):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = dev_env.cmd_up()

        self.assertEqual(calls, ["first", "second-fails", "third"])
        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("OK first:", output)
        self.assertIn("FAIL second-fails:", output)
        self.assertIn("OK third:", output)
        self.assertIn("SKIP Ensure standard test databases", output)

    def test_exit_is_zero_when_every_check_passes_and_postgres_databases_are_ensured(self):
        fake_checks = [
            ("Python >= 3.12", lambda: (True, "ok")),
            ("PostgreSQL reachable", lambda: (True, "ok")),
        ]
        with mock.patch.object(dev_env, "_CHECKS", fake_checks), mock.patch.object(
            dev_env.alpha, "_ensure_database_exists"
        ) as ensure_mock:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = dev_env.cmd_up()
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            ensure_mock.call_args_list,
            [
                mock.call(dev_env._db_url(dev_env.STANDARD_TEST_DB)),
                mock.call(dev_env._db_url(dev_env.ALPHA_DB)),
            ],
        )


@contextlib.contextmanager
def tempdir_web(testcase: unittest.TestCase):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@unittest.skipUnless(_postgres_reachable(), "requires a real local PostgreSQL at 127.0.0.1:5432")
class TestDropAllExclusion(unittest.TestCase):
    """Real PostgreSQL: `testdb --drop-all` must never drop `opportunityos_test`
    or `opportunityos_alpha`, even though probe databases created here share
    the `opportunityos_test_` prefix those two are (deliberately) excluded
    from matching."""

    PROBE_SLUGS = ("f2-dropall-a", "f2-dropall-b")

    def setUp(self):
        for slug in self.PROBE_SLUGS:
            dev_env.alpha._ensure_database_exists(dev_env._db_url(f"{dev_env.TEST_DB_PREFIX}{slug}"))

    def test_drop_all_drops_probe_databases_but_never_the_protected_two(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = dev_env.cmd_testdb_drop_all()
        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        dropped_line = next(
            line for line in output.splitlines() if line.startswith("testdb --drop-all: dropped")
        )
        dropped_names = [
            name.strip().rstrip(".") for name in dropped_line.split("dropped", 1)[1].split(",")
        ]
        for slug in self.PROBE_SLUGS:
            self.assertIn(f"{dev_env.TEST_DB_PREFIX}{slug}", dropped_names)
        self.assertNotIn(dev_env.STANDARD_TEST_DB, dropped_names)
        self.assertNotIn(dev_env.ALPHA_DB, dropped_names)


if __name__ == "__main__":
    unittest.main()
