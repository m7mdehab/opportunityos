# §10 — FR-006 recovery prerequisites (reconciled 2026-09-12)

This file supersedes the stale 2026-09-04 draft. Repository truth at `ec36a453` is authoritative; items already repaired by PR #76 or its merged code are not carried forward as open work.

## 1. Source breadth is still the dominant product blocker

The implementation defect that left registered Greenhouse/Lever boards unbound is fixed: `opportunity.adapters.get_all_standard_adapters()` now derives ATS adapters from read-allowed `SourceRegistry` entries. The Hacker News worker path is also governed and resolves the current `Ask HN: Who is hiring?` thread through the Firebase API rather than treating the `whoishiring` user object as the posting feed.

What is *not* closed is the frozen A-23 outcome: there is still no committed live-run evidence proving >=300 live employment boards and >=8 new read-allowed sources producing real product rows. The last authoritative breadth measurement remains 36/300 boards. Registry entries alone do not count. A source counts only after policy allows reading, a real adapter is bound, permitted live data parses, Opportunity rows persist, and evidence is captured. Reddit remains subject to source policy: official/permitted API or feed only; otherwise it is manual-only/blocked, never scraped around a 403/anti-bot barrier.

## 2. A-9 still requires an actual permitted live poll

The product seam is implemented and CI-covered with fixtures, but the frozen claim requires a real permitted live poll through source -> policy gate -> acquisition -> parse -> normalize -> persist -> evaluate. The historical FR-006 run did not complete that live operation. Fixture success is not a substitute.

## 3. Extraction has an evidence ceiling, not a parser excuse

The committed 540-payload corpus still measures 52.2% work-mode coverage and 72.2% country-or-remote-scope coverage, versus frozen targets of 90% and 85%; uncertainty is 18.5% and passes. The historical provenance split showed 47.8% of payloads had no work-mode signal at all. Do not invent values or alter the corpus to make a percentage. Closure requires either truthful additional native adapter signals over the same corpus or a rigorous demonstrated ceiling showing the frozen threshold cannot be reached without fabrication.

## 4. Title-family coverage remains below the frozen threshold

The committed evidence remains 469/540 = 86.9% mapped against a >=95% target. Residual titles include trades, cross-functional executive roles and genuinely ambiguous postings. Do not grow broad regexes merely to hit the target; use structured/native metadata or a defensible occupational taxonomy, and preserve `other` for ambiguity.

## 5. Historical A-6 scope deviation cannot be rewritten

The frozen historical result remains 740 changed paths, 739 within the pre-committed expected set and one separately dispositioned path. The expected set must not be edited retroactively. Closure must use the repository's accepted-deviation mechanism if one validly applies, otherwise retain the smallest explicit historical governance exception.

## 6. Two artifact validators still require deliberate unification

`truth/validator.py` is the canonical truth authority. `matching/validator.py::ArtifactClaimValidator` still has real outbound callers and represents a second validation surface. Unify callers onto canonical semantics or turn the legacy validator into a compatibility facade, with parity and unsupported-claim regression tests. Truth-lock may not be weakened.

## 7. Readiness-matrix aliases remain unresolved

FR-006 F4 names `1B/1H/2A/2B/2C/3C/3E/1G`, but the readiness matrix is keyed by authoritative `req_id` values. Do not invent mappings. Either trace each alias to an authoritative source or explicitly deprecate it as a dead label with evidence.

## 8. Items no longer open (stale draft corrections)

- ATS board binding: fixed by registry-derived Greenhouse/Lever adapter construction.
- Hacker News policy/wiring: governed worker path resolves the actual current Who Is Hiring thread.
- `stale_postings` cadence: worker scheduler defines and enqueues the `reverify_stale` job and the handler invokes `StaleOpportunityReverifier`.
- `identity.phone` +20 false positive: fixed under ADR-0018 with validator and document-model regressions.
- Playwright stale 20/22 report: current main CI is green after PR #76's browser-coverage repair; the old 20/22 number is historical evidence, not current behavior.
- CI independence/PostgreSQL authentication/State freshness: repaired by PR #76 and green on current main.

## 9. Verification still required before closure

- Re-run the frozen A-1 full real-PostgreSQL suite with **0 skipped**. PR #78 enables the already-required A-15 performance test in that full CI run so it cannot hide as the remaining gated skip.
- Re-run the standalone `api` suite repeatedly to determine whether the historical idle-in-transaction hang still exists; do not assume the old diagnosis.
- Re-run A-20 clustering against the complete committed corpus, not a hand fixture.
- Run A-11 guard-neutralisation independently of the implementation report if the protocol still reserves that independence property.
- Reconcile `REPORT-FR-006.md`, generated `docs/STATE.md`, `docs/CHAT_RESUME.md`, and roadmap only from fresh evidence.

## 10. Process constraints remain binding

Maximum four substantial concurrent workers/process groups. Use isolated databases for parallel database workers. Partition work by behavioral seam. Do not weaken gates, fabricate evidence, retry around 403/429/CAPTCHA/MFA, commit private Founder data, or start BRIEF-007 before the Founder personally validates Founder Web Alpha.
