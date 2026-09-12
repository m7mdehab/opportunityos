# REPORT — BRIEF-FR-006: Nothing Missed, Nothing Hidden, Nothing Ugly

**Brief:** `briefs/BRIEF-FR-006.md` v1.1 · **Protocol:** `docs/AGENT_EXECUTION_PROTOCOL.md` v2
**Recovery branch:** `fix/fr006-final-closure` · **PR:** #78
**Date:** 2026-09-13

## 1. Summary

The bounded recovery is complete as far as the frozen corpus and current source policy truthfully permit. All deterministic product, migration, governance, State, source-policy, truth-lock, and browser gates are green at PR run `34724239556` and companion runs. The final Linux backend checkpoint ran **1095 tests**, with zero failures, zero errors, and zero skips.

The recovery closed the live-poll gap, current title-family target, browser preview regression, live-board target, stale-posting cadence, and duplicate-validator semantic divergence. It did not invent missing work-mode evidence or claim product rows that were never persisted.

Two frozen acceptance outcomes remain explicit:

- A-12 work-mode coverage reaches an honest signal ceiling of 419/540 (77.6%), below 90%; the other A-12 thresholds pass.
- A-23 proves 334 live relevant boards, above 300, but proves 0/8 new read-allowed sources producing persisted Opportunity rows in the bounded live session. Reddit remains policy-blocked/manual-only and the freelance manual deep-link alternative is preserved.

A-6 remains an accepted historical exception under ADR-0020. A-20's exact Cloudflare Senior Customer Engineer subset is absent from the frozen 540-payload corpus, so the requested subset member count cannot be manufactured; the full-corpus invariants pass and the absence is a recorded historical corpus/contract exception.

## 2. Decision

`PASS_WITH_NOT_CLOSED`

All remediable engineering is complete and the branch is ready to merge. `NOT_CLOSED` rows remain visible because frozen thresholds and policy outrank a cosmetic terminal label. Founder Web Alpha validation is the next human boundary; BRIEF-007 / Phase 6 remains blocked.

## 3. Acceptance ledger

| Claim | Status | Current evidence |
|---|---|---|
| A-0 | PASS | Fail-closed persistence invariant remains covered in the green 1095-test suite. |
| A-1 | PASS | Linux/PostgreSQL: **1095 tests**, 0 failures, 0 errors, **0 skipped**; N > 672. |
| A-2 | PASS | The single full-suite test-id execution completed at 1095 without duplicate/failing discovery. |
| A-3 | PASS | Fresh PostgreSQL migration reaches head `0005_widen_location_region`; migration compatibility tests pass. |
| A-4 | PASS | Governance, Guard, and repository-integrity checks pass. |
| A-5 | PASS | Generated State freshness passes; `docs/STATE.md` is generator-owned. |
| A-6 | HISTORICAL_EXCEPTION | Frozen history remains 740 changed paths: 739 expected, one historical `opportunityos.db`, later removed and ignored; ADR-0020 accepted. |
| A-7 | PASS | Web build and lint pass. |
| A-8 | PASS | Playwright **22/22** passes. |
| A-9 | PASS | Permitted Himalayas live poll: 20 fetched/parsed/persisted/evaluated; zero fixture rows. |
| A-10 | PASS | 30 artifacts across two synthetic packs and three templates, DOCX/PDF, zero validator rejections. |
| A-11 | PASS | Truth-lock and guard-neutralisation evidence retained; canonical validator tests pass. |
| A-12 | NOT_CLOSED | N=540; work mode 419/540 (77.6%, target 90%, honest ceiling); country/scope 532/540 (98.5%); uncertain 56/540 (10.4%). |
| A-13 | PASS | Title family 532/540 (98.5%, target 95%); 8 honest residual titles; Senior Customer Engineer 46.08 ranks below Senior Data Engineer 82.5. |
| A-14 | PASS | 14/15 facets available; unavailable language dimension remains explicitly unavailable rather than fabricated. |
| A-15 | PASS | Required 20k PostgreSQL search p95 **16.14 ms** (<200 ms); performance test ran inside the zero-skip suite. |
| A-16 | PASS | Source Registry permissions unchanged in meaning; all registered ATS reads remain policy-gated and prepare/submit disabled. |
| A-17 | PASS | Predicate contract and unsupported-claim rejection pass after validator unification. |
| A-18 | PASS | Filters/facets preserve decisions and do not re-judge opportunities. |
| A-19 | PASS | Provenance idempotency passes in the full suite. |
| A-20 | HISTORICAL_EXCEPTION | Full corpus: 540 opportunities, 249 families, cross-employer=0, cross-title=0, deterministic=true, raw/show-separately preserved. Exact Cloudflare subset count=0 because no such corpus rows exist. |
| A-21 | PASS | Card accessibility/keyboard/browser coverage passes with Playwright 22/22. |
| A-22 | PASS | 409 rejection renders claim and reason in plain language; binary preview/API/browser coverage passes. |
| A-23 | NOT_CLOSED | Live relevant boards **334/300 PASS**; exact seed pool 482, 309 live, 286 newly registered. New persisted row-producing sources **0/8**. HN production path is governed/mock-proven but no live HN rows were captured in this session; Reddit is BLOCKED_POLICY/manual-only; at least two freelance manual deep links remain available. |

## 4. Key measurements

| Measure | Result |
|---|---|
| A-1 | 1095 tests; failures=0; errors=0; skipped=0 |
| A-8 | 22/22 Playwright |
| A-9 | Himalayas; fetched=20; parsed=20; persisted=20; evaluated=20; fixture rows=0 |
| A-12 | N=540; work=77.6%; country/scope=98.5%; uncertain=10.4%; adapter=33.3%; inference=44.3%; no-signal=22.4% |
| A-13 | 532/540 mapped=98.5%; other=8; ranking 46.08 < 82.5 |
| A-20 | exact Cloudflare members=0/ABSENT; cross-employer=0; cross-title=0; deterministic=true; show-separately/raw-data tests pass |
| A-23 | 334/300 live boards; 0/8 new persisted row-producing sources; HN no live row evidence; Reddit BLOCKED_POLICY; freelance manual deep-link alternative satisfied |

## 5. Adjacent blockers

| Item | Result |
|---|---|
| Standalone API lifecycle | PASS — 124 tests, zero skips, completed three times; no PostgreSQL sessions remained. |
| Validator architecture | PASS — ADR-0021; outbound compatibility facade delegates canonical truth semantics; targeted independent review PASS after unknown scalar/record predicate regressions were added. |
| Stale postings | PASS — durable queue timestamps enforce first tick, <24h suppression, >=24h enqueue, retry/pending dedupe, and fresh-process cadence. |
| `+20` phone parsing | PASS — ADR-0018 and regressions retained. |
| Synthetic fixture | PASS — engineering uses the synthetic founder-shaped graph only; no private Founder Truth Pack was read or committed. |
| Readiness aliases | PASS — ADR-0019 deprecates undocumented aliases without inventing mappings. |

## 6. Evidence

- A-9: `reports/evidence/FR-006/a9-live-poll-2026-09-12.md`, immutable run `34720287787`.
- A-12: `reports/evidence/FR-006/closure-current/a12-extraction.md`.
- A-23: `reports/evidence/FR-006/closure-current/a23-exact-seed-probe.json`, immutable run `34722384079`; exact seed revisions are pinned in `docs/SOURCE_EVIDENCE.md`.
- Final integration: run `34724239556`; companion State, Guard, Mirror, and bounded live-evidence checks all pass.

## 7. Next phase prerequisites

Founder Web Alpha validation is next. Use the real private Founder Truth Pack only in the founder-controlled environment and validate useful daily opportunity yield, work-mode/location clarity, duplicate collapse, artifact quality, and safe outbound behavior. Do not start BRIEF-007 / Phase 6 until the Founder personally validates and accepts Founder Web Alpha.
