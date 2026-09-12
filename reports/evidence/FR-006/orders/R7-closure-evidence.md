# Work order R7 — final claim capture, independent adjudication, and state inputs

## Authority and objective

BRIEF-FR-006 recovery Phases F-H. After R1-R6 are integrated, capture every frozen
claim at the exact candidate SHA, independently re-execute high-consequence claims,
and reconcile authoritative report/evidence inputs without rewriting history.

## Owned behavior seam

Candidate commit -> raw test/evidence artifacts -> independent verdict -> report,
readiness matrix, ledger/deviation addendum -> generated State.

## Allowed files

- `reports/evidence/FR-006/closure-current/**`
- `reports/REPORT-FR-006.md`
- `reports/evidence/FR-006/LEDGER.md`
- `reports/evidence/FR-006/deviations.md`
- `reports/evidence/FR-006/next-prerequisites-draft.md`
- `reports/evidence/FR-006/founder-packet-draft.md`
- `reports/FOUNDER_READINESS_MATRIX.json` and generated `.md`
- `docs/CHAT_RESUME.md`
- generated `docs/STATE.md` only via `scripts/generate_state.py`

No production code, fixture, threshold, frozen claim, or historical expected-scope
edit is allowed.

## Mandatory treatment

- A-6 compares `bf25d93...candidate`, preserves the immutable expected set, lists and
  dispositions every extra, and remains `NOT_CLOSED` if any extra exists.
- Dead aliases `1B/1H/2A/2B/2C/3C/3E/1G` must not be guessed. Record their absence
  from authoritative history, explicitly deprecate them, and update only stable
  subject-matched `req_id` rows.
- Distinguish old observation/current observation/change/current status for A-0..A-23.
- Independent checker must re-run validator/phone, source policy/adapters, scoring,
  DB isolation, A-11 mutation, and state/evidence integrity. Neutralised guard must
  break >=2 suites, restore byte-identically, then return green and 409/no bytes.
- Generate readiness Markdown and State using supported scripts; run freshness tests.
- Terminal report decision may be `PASS` only if every frozen claim is actually
  satisfied under its wording. Otherwise keep `PASS_WITH_NOT_CLOSED` and distinguish
  irreducible exceptions from unfinished engineering.

## Acceptance

Run all CLAIMS.md commands, standalone API twice, full PostgreSQL suite, migration
round trip, guard/repository, build, lint, Playwright, State generation/freshness, and
all newer mandatory CI gates. Store finished logs rather than piping summaries away.

Commit the reconciled evidence only after the independent verdict names the exact SHA.
