# Work order F2 — `scripts/dev_env.py`

**Brief:** BRIEF-FR-006 §2 Track 0. **Wave:** 0 (sequential, before wave 1).
**Worktree:** `wt/fr006-f2` **Branch:** `wt/fr006-f2` **Test DB:** `opportunityos_test_f2`

## Deliverable text (verbatim from the brief)

> **F2 (moved here) — `scripts/dev_env.py`.** `up` verifies Python ≥ 3.12, Node LTS,
> PostgreSQL reachable, Playwright browsers, and a PDF renderer, and prints exactly what to
> fix; `testdb <slug>` creates `opportunityos_test_<slug>` and prints the DSN;
> `testdb --drop-all`; `doctor` is the founder-facing alias. `alpha.py` and every child
> process use `sys.executable`.

## Environment facts (established by the Master; do not re-derive)

- Python 3.12.10 is `py -3.12`; **bare `python` on this machine is 3.10.3 and must never be
  used**. All project deps (sqlalchemy 2.0.52, psycopg2, python-docx, reportlab, pdfplumber,
  fastapi, alembic) are installed in the 3.12 interpreter. There is no virtualenv.
- PostgreSQL 16.10 portable cluster at `%LOCALAPPDATA%\opos-pg\pgsql`, host `127.0.0.1:5432`,
  role `opportunityos`, trust auth, maintenance db `postgres`.
- Node v24.18.0 / npm 11.16.0; `web/node_modules` is installed; Playwright is the npm
  `@playwright/test` package (there is no Python playwright).
- **PDF renderer decision, already made by the Master: `reportlab`.** It is a pinned
  dependency in `pyproject.toml`, pure-Python, needs no admin rights, and is deterministic.
  LibreOffice is NOT installed and must not be required. `dev_env.py up` checks that
  `import reportlab` succeeds and reports the version; it must NOT check for `soffice`.
- `scripts/alpha.py` already defines `ALPHA_DB_NAME = "opportunityos_alpha"`,
  `_ensure_database_exists(db_url)` and `_refuse_test_database`. Reuse those helpers rather
  than writing a second database-creation path.

## Required behaviour

1. `python scripts/dev_env.py up` — checks, in order, printing one line per check with
   `OK` / `FAIL` and, on FAIL, the exact command to fix it:
   Python ≥ 3.12 (report `sys.version`), Node present with version, npm present,
   PostgreSQL reachable (connect to the maintenance db and `SELECT version()`),
   `web/node_modules` present, Playwright browsers installed
   (`npx playwright install --dry-run` or equivalent non-mutating probe; if you cannot probe
   without installing, run `npx playwright install chromium` and say so), and the PDF
   renderer (`reportlab`). Creates the standard test databases `opportunityos_test` and
   `opportunityos_alpha` if absent. **Exit 0 only when every check is OK**; otherwise exit 1
   after printing all failures (do not stop at the first).
2. `python scripts/dev_env.py testdb <slug>` — creates `opportunityos_test_<slug>` if absent
   (idempotent), and prints **only** the DSN on the last line so a caller can capture it.
   Slug is validated: `[a-z0-9-]{1,32}` and nothing else; reject anything else non-zero.
3. `python scripts/dev_env.py testdb --drop-all` — drops every database matching
   `opportunityos_test_%` **except** `opportunityos_test` and `opportunityos_alpha`,
   terminating open backends first (`pg_terminate_backend`), and prints what it dropped.
4. `python scripts/dev_env.py doctor` — an alias for `up`.
5. **`sys.executable` sweep:** every place in `scripts/alpha.py` (and `worker/` if any) that
   spawns a Python child process must use `sys.executable`, never the literal `"python"`.
   Grep for it; fix every hit; add a unit test that asserts no `"python"` literal remains as
   a subprocess argv[0] in `scripts/alpha.py`.

## Allowed files

- `scripts/dev_env.py` (new)
- `scripts/test_dev_env.py` (new)
- `scripts/alpha.py` (the `sys.executable` sweep only — no other change)
- `scripts/test_alpha.py` (assertions for the sweep only)

## Frozen — touching any of these is a FAIL

Everything else. Specifically: `storage/`, `api/`, `matching/`, `opportunity/`, `truth/`,
`web/`, migrations, `AGENTS.md`, `docs/`, and any file under `private/`.

## Acceptance rows

| # | Command | Expected |
|---|---|---|
| F2.1 | `py -3.12 scripts/dev_env.py up` | exit 0; one line per check; the PDF-renderer line names reportlab and its version; no line mentions LibreOffice/soffice |
| F2.2 | `py -3.12 scripts/dev_env.py testdb f2probe` | exit 0; last line is a `postgresql+psycopg2://...opportunityos_test_f2probe` DSN; running it twice is exit 0 both times |
| F2.3 | `py -3.12 scripts/dev_env.py testdb --drop-all` | exit 0; prints the dropped list; `opportunityos_test` and `opportunityos_alpha` are NOT in it |
| F2.4 | `py -3.12 scripts/dev_env.py testdb 'Bad Slug'` | non-zero exit, message names the allowed pattern |
| F2.5 | `py -3.12 -m unittest scripts.test_dev_env -v` | `OK`, ≥ 6 tests |
| F2.6 | `py -3.12 -m unittest scripts.test_alpha -v` | `OK`, count ≥ the count on main (state both) |

Paste the raw `Ran N tests` / `OK` lines. Do not summarise.
