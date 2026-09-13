# Public repository exposure audit

Executed 2026-09-13 before merging PR #79, after the repository became public.

## Automated controls

- Repository integrity check: PASS.
- Guard and mirror-boundary checks: PASS locally and in PR run `34750289106`
  attempt 2.
- Gitleaks 8.30.1 scanned all 641 reachable commits and approximately 15.36 MB
  with redaction enabled. It reported seven candidates; each was adjudicated as
  synthetic test/evidence text rather than a credential:
  - four identical `determinism: ... identical=True` test-output lines;
  - one runtime-generated synthetic API-test password;
  - two deliberately fake token/API-key strings used to test log redaction.

## Focused tracked-content review

- `private/` tracks only `README.md` and `watchlist.yaml.template`.
- No tracked `.env`, PEM/key/certificate, credential JSON/YAML, log, SQLite,
  PostgreSQL dump, or Founder `truth_pack.yaml` file exists.
- No non-test hard-coded password, session secret, provider/API token, private
  database DSN, or production credential matched the focused credential scan.
- Deployment manifests contain only generated-secret directives and replacement
  placeholders. The public URL is intentionally documented; its credential is not.
- Public source fixtures contain public job-posting text and synthetic tests contain
  explicit fake identities. No private Founder Truth Pack or Founder profile data is
  present.
- The externally served HTML contains neither the database URL nor the session-secret
  environment-variable name. Unauthenticated application APIs return 401.

Result: **PASS — no secret or private Founder data exposure found.**
