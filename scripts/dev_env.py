"""``python scripts/dev_env.py up|doctor|testdb`` -- local dev environment checks
and test-database management.

``up`` (``doctor`` is a founder-facing alias for the identical behaviour) verifies,
in order, that this machine has everything ``scripts/alpha.py`` and the test suite
need: Python >= 3.12, Node, npm, a reachable PostgreSQL, ``web/node_modules``,
Playwright's chromium browser, and the PDF renderer (``reportlab`` -- a pinned,
pure-Python dependency in ``pyproject.toml``; LibreOffice/``soffice`` is
deliberately never checked for, and is not required). It prints exactly one
``OK``/``FAIL`` line per check, never stops at the first failure (every check
always runs), and exits 0 only when every check passed. If PostgreSQL is
reachable, it also creates the two standard databases this project's own
tooling expects (``opportunityos_test``, ``opportunityos_alpha``) if either is
absent, reusing ``scripts.alpha._ensure_database_exists`` rather than a second
database-creation code path.

``testdb <slug>`` creates ``opportunityos_test_<slug>`` if it does not already
exist (idempotent -- running it twice is exit 0 both times) and prints, on its
own last line, the ``postgresql+psycopg2://`` DSN a caller can capture. The
slug is validated against ``[a-z0-9-]{1,32}`` before anything touches
PostgreSQL; anything else is rejected with a non-zero exit and a message
naming the allowed pattern.

``testdb --drop-all`` drops every database whose name matches
``opportunityos_test_%`` -- terminating any open backends on it first via
``pg_terminate_backend`` -- except ``opportunityos_test`` and
``opportunityos_alpha`` themselves (neither actually matches that pattern,
since it requires a `_test_` prefix; both are still named explicitly here as
a second, explicit safeguard rather than relying on the pattern alone), and
prints what it dropped.

Every child process this module spawns for a Python interpreter uses
``sys.executable``, never a literal ``"python"`` -- see ``scripts/alpha.py``'s
own docstring on why that matters on this machine (bare ``python`` here is an
older interpreter missing this project's dependencies).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
# scripts/__init__.py makes "scripts" a real package under REPO_ROOT; ensure
# REPO_ROOT is importable regardless of how this file itself was invoked
# (``python scripts/dev_env.py`` puts only scripts/ itself, not REPO_ROOT, on
# sys.path[0]) so ``import scripts.alpha`` below resolves this worktree's own
# copy rather than failing or -- worse -- resolving some other checkout.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WEB_DIR = REPO_ROOT / "web"

import scripts.alpha as alpha  # noqa: E402 -- must follow the sys.path fix above

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_ROLE = "opportunityos"
PG_MAINTENANCE_DB = "postgres"

STANDARD_TEST_DB = "opportunityos_test"
ALPHA_DB = alpha.ALPHA_DB_NAME  # "opportunityos_alpha"

TEST_DB_PREFIX = "opportunityos_test_"
SLUG_PATTERN = "[a-z0-9-]{1,32}"
_SLUG_RE = re.compile(f"^{SLUG_PATTERN}$")


def _db_url(db_name: str) -> str:
    """Build the trust-auth local DSN for ``db_name`` (host/port/role fixed --
    see this module's own docstring)."""
    return f"postgresql+psycopg2://{PG_ROLE}@{PG_HOST}:{PG_PORT}/{db_name}"


def _maintenance_url() -> str:
    return _db_url(PG_MAINTENANCE_DB)


# ---------------------------------------------------------------------------
# up / doctor checks
# ---------------------------------------------------------------------------


def _check_python() -> tuple[bool, str]:
    ok = sys.version_info >= (3, 12)
    version = sys.version.split()[0]
    if ok:
        return True, f"Python {version} (sys.version={sys.version!r})"
    return False, (
        f"Python {version} (sys.version={sys.version!r}) is older than 3.12. Fix: invoke every "
        "command in this project with `py -3.12` -- bare `python` on this machine may resolve to "
        "an older interpreter missing this project's dependencies."
    )


def _check_node() -> tuple[bool, str]:
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return False, (
            "Node.js not found on PATH. Fix: install Node LTS from https://nodejs.org/ and ensure "
            "`node` is on PATH."
        )
    if result.returncode != 0:
        return False, f"`node --version` exited {result.returncode}. Fix: reinstall Node LTS."
    return True, f"Node {result.stdout.strip()}"


def _check_npm() -> tuple[bool, str]:
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    try:
        result = subprocess.run([npm_cmd, "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return False, (
            "npm not found on PATH. Fix: install Node LTS (bundles npm) from https://nodejs.org/."
        )
    if result.returncode != 0:
        return False, f"`npm --version` exited {result.returncode}. Fix: reinstall Node LTS."
    return True, f"npm {result.stdout.strip()}"


def _check_postgres() -> tuple[bool, str]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
    except SQLAlchemyError as exc:
        return False, (
            f"PostgreSQL not reachable at {PG_HOST}:{PG_PORT} (role {PG_ROLE!r}, maintenance db "
            f"{PG_MAINTENANCE_DB!r}): {exc}. Fix: start the portable cluster (see "
            "briefs/BRIEF-FR-003.md section 6) or your own PostgreSQL server on that host/port, "
            "then retry."
        )
    finally:
        engine.dispose()
    return True, f"PostgreSQL reachable at {PG_HOST}:{PG_PORT} ({version})"


def _check_node_modules() -> tuple[bool, str]:
    path = WEB_DIR / "node_modules"
    if path.exists():
        return True, f"{path} present"
    return False, f"{path} missing. Fix: run `npm install` in {WEB_DIR}."


_PLAYWRIGHT_INSTALL_LOCATION_RE = re.compile(r"Install location:\s*(.+)")


def _check_playwright_browsers() -> tuple[bool, str]:
    """Non-mutating probe: ``npx playwright install --dry-run chromium`` never
    downloads anything by itself (that is what ``--dry-run`` means) -- it only
    prints the install plan, including each component's own on-disk
    ``Install location:``. This check runs that probe, then verifies those
    exact paths already exist on disk; it never runs a mutating
    ``npx playwright install`` itself.
    """
    if not (WEB_DIR / "node_modules").exists():
        return False, (
            f"{WEB_DIR / 'node_modules'} is missing, so Playwright browsers cannot be probed. "
            f"Fix: run `npm install` in {WEB_DIR} first."
        )
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    try:
        result = subprocess.run(
            [npx_cmd, "playwright", "install", "--dry-run", "chromium"],
            cwd=str(WEB_DIR),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "npx not found on PATH. Fix: install Node LTS (bundles npx)."
    if result.returncode != 0:
        return False, (
            f"`npx playwright install --dry-run chromium` exited {result.returncode}: "
            f"{result.stderr.strip()}. Fix: cd {WEB_DIR} && npx playwright install chromium."
        )
    locations = [Path(loc.strip()) for loc in _PLAYWRIGHT_INSTALL_LOCATION_RE.findall(result.stdout)]
    if not locations:
        return False, (
            "Could not parse `npx playwright install --dry-run chromium` output for install "
            f"locations. Fix: cd {WEB_DIR} && npx playwright install chromium."
        )
    missing = [str(loc) for loc in locations if not loc.exists()]
    if missing:
        return False, (
            f"Playwright browser component(s) not yet downloaded: {', '.join(missing)}. "
            f"Fix: cd {WEB_DIR} && npx playwright install chromium."
        )
    return True, (
        "Playwright chromium browsers already installed (probed non-mutating via `npx playwright "
        "install --dry-run chromium`, verified each reported install location exists on disk)."
    )


def _check_pdf_renderer() -> tuple[bool, str]:
    try:
        import reportlab
    except ImportError as exc:
        return False, (
            f"`import reportlab` failed: {exc}. Fix: `py -3.12 -m pip install -e .` from the repo "
            "root (reportlab is already a pinned dependency in pyproject.toml)."
        )
    version = getattr(reportlab, "Version", "unknown")
    return True, f"reportlab {version} importable (PDF renderer)"


_CHECKS: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("Python >= 3.12", _check_python),
    ("Node.js", _check_node),
    ("npm", _check_npm),
    ("PostgreSQL reachable", _check_postgres),
    ("web/node_modules", _check_node_modules),
    ("Playwright browsers", _check_playwright_browsers),
    ("PDF renderer (reportlab)", _check_pdf_renderer),
]


def cmd_up() -> int:
    all_ok = True
    postgres_ok = False
    # Every check always runs, in order, regardless of an earlier failure --
    # a founder fixing their machine needs the full list of what is wrong in
    # one pass, not one failure per re-run.
    for name, check in _CHECKS:
        ok, detail = check()
        print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
        if not ok:
            all_ok = False
        elif name == "PostgreSQL reachable":
            postgres_ok = True

    if postgres_ok:
        for db_name in (STANDARD_TEST_DB, ALPHA_DB):
            try:
                alpha._ensure_database_exists(_db_url(db_name))
            except alpha.AlphaError as exc:
                print(f"FAIL Ensure database {db_name!r} exists: {exc}")
                all_ok = False
    else:
        print(
            "SKIP Ensure standard test databases exist: PostgreSQL is not reachable (see the FAIL "
            "line above)."
        )

    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# testdb
# ---------------------------------------------------------------------------


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise SystemExit(
            f"testdb: invalid slug {slug!r} -- must match {SLUG_PATTERN} (lowercase letters, "
            "digits, and hyphens only, 1-32 characters)."
        )


def cmd_testdb_create(slug: str) -> int:
    _validate_slug(slug)
    db_name = f"{TEST_DB_PREFIX}{slug}"
    db_url = _db_url(db_name)
    try:
        alpha._ensure_database_exists(db_url)
    except alpha.AlphaError as exc:
        print(f"testdb: FAILED to create/verify {db_name!r}: {exc}", file=sys.stderr)
        return 1
    # Only the DSN on the last line, so a caller can capture it (e.g. `dsn=$(... | tail -n 1)`).
    print(db_url)
    return 0


def cmd_testdb_drop_all() -> int:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    protected = {STANDARD_TEST_DB, ALPHA_DB}
    engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT datname FROM pg_database WHERE datname LIKE :pattern"),
                {"pattern": f"{TEST_DB_PREFIX}%"},
            ).scalars().all()
            # `LIKE 'opportunityos_test_%'` already cannot match either protected
            # name (both are missing the required trailing `_test_...` shape),
            # but both are excluded explicitly here too, as a second, independent
            # safeguard -- never relying on the LIKE pattern alone to protect them.
            to_drop = sorted(name for name in rows if name not in protected)
            if not to_drop:
                print("testdb --drop-all: nothing to drop.")
                return 0
            for db_name in to_drop:
                # CREATE DATABASE cannot run while other backends are connected;
                # DROP DATABASE has the identical restriction -- terminate any
                # open connections to db_name first.
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": db_name},
                )
                # db_name comes only from pg_database itself (never external
                # input), double-quoted below as a SQL identifier -- DROP
                # DATABASE does not accept a bind parameter for the name.
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            print(f"testdb --drop-all: dropped {', '.join(to_drop)}.")
            return 0
    except SQLAlchemyError as exc:
        print(f"testdb --drop-all: FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/dev_env.py",
        description=(
            "Local dev environment checks (`up`/`doctor`) and test-database management (`testdb`)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up", help="Verify the local dev environment; create standard test databases if absent.")
    sub.add_parser("doctor", help="Alias for `up` (founder-facing name).")
    testdb = sub.add_parser("testdb", help="Create or drop opportunityos_test_<slug> databases.")
    group = testdb.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "slug",
        nargs="?",
        default=None,
        help=f"Create opportunityos_test_<slug> ({SLUG_PATTERN}) if absent; prints its DSN.",
    )
    group.add_argument(
        "--drop-all",
        action="store_true",
        help="Drop every opportunityos_test_* database except opportunityos_test and opportunityos_alpha.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command in ("up", "doctor"):
        return cmd_up()
    if args.command == "testdb":
        if args.drop_all:
            return cmd_testdb_drop_all()
        if args.slug is None:
            print("testdb: a slug or --drop-all is required.", file=sys.stderr)
            return 2
        return cmd_testdb_create(args.slug)
    return 2  # unreachable: argparse's `choices`/subparsers already reject anything else


if __name__ == "__main__":
    raise SystemExit(main())
