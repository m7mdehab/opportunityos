# FR-007 W23.1 Founder Surface Acceptance Correction

## Branch and baseline

- Branch: `work/fr007-codex-founder-surface-corrections`
- W23.1 checkout baseline: `3466c51e6579d263e427876643a5d6bf27803303`
- Reviewed W23 implementation head: `eae8b966e4da9fda148e82485dd8d529f9ae182d`
- This report records the W23.1 correction package; FR-007 closure is not claimed.

## F1–F7 acceptance

- **F1 PASS** — repaired the header-strip mojibake and added a UTF-8/source scan over web source files; no `â€`, `Ã`, or replacement-character markers remain.
- **F2 PASS** — `founder_source_overview` is schedule-led, includes scheduled zero rows, preserves schedule health fields, and includes an explicit manual catalogue. The UI aggregates concrete board counts, shows the all-source total, labels manual families `Manual only · 0 automated`, and routes them to the existing manual-check flow. Reddit has no automated schedule.
- **F3 PASS** — Greenhouse board sweep derives only standard Greenhouse board roots, performs one request per board, marks only definitive 404/410/exact tombstone responses stale, preserves ambiguous 403/429/network/5xx/redirect/near-miss/custom-domain results, and records re-verification. It is wired into the existing reverify maintenance handler.
- **F4 PASS** — dashboard Hidden counts distinct current-day, non-stale canonical feed rows with policy visibility reasons and excludes `facet:` reasons. Hosted feed defaults to visible, non-stale rows; `include_hidden=true` includes hidden non-stale rows; `hidden_count` is sourced from the hidden query and `hidden_by` is derived from policy reasons.
- **F5 PASS** — source overview opportunity counts include only visible, non-stale feed rows.
- **F6 PASS** — detail modal has explicit desktop grid placement, a full-width header with numeric score, and a bounded mobile `dvh` one-column layout with dialog outside/Escape handling.
- **F7 PASS** — behavioral coverage was added for the Greenhouse response matrix, source schedule/manual aggregation fixture, hosted visible/hidden route contract, and numeric drawer score assertion; existing static guards remain.

## Proof results

- `python -m unittest scripts.test_w23_founder_surface -v`: PASS (6 tests).
- `python -m unittest opportunity.test_reverification -v`: PASS (12 tests).
- `python -m unittest storage.test_hosted_runtime_migration scripts.test_fr007_supabase_execution_bundle scripts.test_fr007_supabase_execution_postgres -v`: PASS; disposable PostgreSQL test is enabled only in the CI proof job and is locally reported as an explicit skip when `OPOS_LIVE_PROOF_TEST` is absent.
- Baseline/restore/portability regression suite: PASS (27 tests).
- `python scripts/fr007_supabase_execution_bundle.py generate`: PASS; final revision `0015_hosted_founder_surface`.
- `python scripts/fr007_supabase_execution_bundle.py verify`: PASS; 15 migration artifacts verified.
- `npm run lint`: PASS.
- `npm run build`: PASS.
- `git diff --check`: PASS.
- UTF-8 scan: PASS; source scan excludes generated `.next` and dependency trees and rejects invalid UTF-8 or the three known mojibake markers.
- Playwright desktop/mobile acceptance: executed through the repository `test.yml` Chromium job (desktop viewport plus the existing 360px and 1280px screenshot cases); final workflow conclusion is recorded below after the pushed run.

## Sanitized behavioral fixtures

Source overview fixture proves `greenhouse:one` scheduled with zero rows, `greenhouse:two` with one visible current row, `lever:empty` with zero rows, and `reddit` as manual-only with zero automated jobs. Family counts sum concrete rows and exclude manual catalogue rows from automated totals.

Greenhouse stale matrix: 404, 410, and exact board marker are stale; 403, 429, 500, network failure, redirects, near misses, and custom domains are preserved. No rows are deleted.

Hosted feed contract: default query uses `visible=eq.true` and `is_stale=eq.false`; `include_hidden=true` removes the visible restriction while keeping `is_stale=eq.false`; hidden count queries `visible=eq.false`; all returned IDs remain bounded to the requested page. Unevaluated/null rows cannot be surfaced as qualified by this projection path.

## Unresolved

No unresolved implementation blocker. Hosted production data and Founder state are outside this correction packet and are not claimed here.

## Final readiness

READY. Final commit: `ca97b29701e19339592a4575da1f1fe59a061693`.

Remote proof: `git ls-remote origin refs/heads/work/fr007-codex-founder-surface-corrections` returned the same SHA.

- Mandatory Governance & Test Suite: run `35511180581` SUCCESS; governance job `106079250719` SUCCESS, web-build-lint-playwright job `106079250816` SUCCESS, backend job `106079250820` SUCCESS.
- Disposable PostgreSQL portability/provider proof: run `35510091256` SUCCESS.
- The mandatory web job executed the complete Chromium suite, including desktop feed behavior and the existing 360px and 1280px mobile/desktop screenshot cases. Its Playwright report artifact was uploaded by CI.
- The mandatory backend job executed the full repository discovery suite (the previous diagnostic run reported 1,407 tests with 1 failure and 2 errors before the final syntax, cross-platform Truth Pack, and backup authorization repairs; the final rerun concluded SUCCESS).

W23.1 is repository-accepted on this branch. No hosted production state or FR-007 closure is claimed.
