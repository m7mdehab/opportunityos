# BC Final Canary Supply Gate — 2026-10-01

> Historical checkpoint only. This stop report is superseded by [`BC-CLOSURE-LIVE-2026-10-02.md`](BC-CLOSURE-LIVE-2026-10-02.md): the replay corpus was subsequently completed from retained production evidence, CI passed without branch-introduced regression, and PRs #196/#197 deployed the bounded production correction. Its source-selection question and stop decision are not current instructions.

## Decision

**STOP before production canary, adapter implementation, PR, merge, or deployment.** The frozen five-candidate set required by the final canary order cannot be reproduced from captured payloads in the repository, and the one bounded ShyftLabs Lever response produced no Egypt-compatible For You candidates. No production writes or queue/scheduler operations were performed.

## State verified

- Active branch: `work/bc-final-geo-capacity` at `7fae7f7847ef986e54e89ef1d5a310314005dc7e`.
- `origin/main`: `63c5d027e3e4e0f9936e126d94829d106c160e2e`.
- Remote branches: `main`, `work/bc-final-geo-capacity`.
- `gh pr list` could not authenticate (`gh auth login` required); the known branch state has no open PR from prior verification. This did not affect the supply decision.
- Last evidenced live DB size from maintenance verification: `381,693,075` bytes (`364.01 MiB`); this was not remeasured because the canary gate failed and no production write was authorized.

## Frozen five-set audit

The final canary order names four Workable candidates and one Teamtailor Appsilon candidate. The registry records aggregate funnel counts and the four Workable titles, but no saved source payload or candidate evidence fixture was found in the current branch for either probe. No Appsilon row appears in the frozen replay fixtures. Therefore none of those five can be independently rerun through the current branch from repository evidence; the registry summaries are not a reproducible candidate set.

Reported Workable candidates (four, two employers):

- Open-Source Machine Learning Engineer — Hugging Face
- Senior Machine Learning Engineer, Voice Agents — Hugging Face
- Senior Open-Source Python Engineer, ML Developer Tools — Hugging Face
- Senior Data Engineer — Hack The Box

The Teamtailor registry records one provisional For You result from 77 postings, but its posting identity, source-native evidence, and application route are absent from the fixtures. It cannot be counted as an independently validated fifth candidate. The prior final canary order explicitly says to stop if that candidate fails revalidation.

## One bounded Lever response

One saved HTTP 200 response from `https://api.lever.co/v0/postings/shyftlabs?mode=json` was parsed without another request. The adapter and corrected in-memory replay were run in order: Unicode-safe source normalization, role relevance, geography, credential requirements, application access, identity dedupe, recommendation.

| Stage | Count |
|---|---:|
| Raw postings | 23 |
| Parsed / unique | 23 / 23 |
| Core or adjacent | 11 |
| Egypt-compatible | 0 |
| Credential-clean | 23 (11 of 11 target-family postings) |
| Classifier-actionable Lever route | 23 (11 of 11 target-family postings) |
| Final For You | 0 |
| For You employers | 0 |
| Recommendation states | 22 Excluded, 1 Review |

The 11 relevant titles were:

| Title | Organization | Corrected result |
|---|---|---|
| AI Engineer Intern | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Associate AI Engineer | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Data Engineer | Shyftlabs | Review — no explicit Egypt-compatible applicant scope |
| Data Engineer | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Data Engineer | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Data Engineer -Databricks | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Data Scientist | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Lead Data Engineer - Databricks | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Senior AI Engineer | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Senior Data Analyst | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |
| Senior Data Engineer | Shyftlabs | Excluded — required onsite/hybrid outside Egypt |

The remaining 12 postings were non-target/unknown and did not enter For You. No posting was persisted. The temporary response body is removed after this report and registry observation are recorded.

## Verification and production boundary

- `python -m pytest tests/test_bc_production_replay.py -q` — **7 passed**.
- PostgreSQL/backend main-versus-branch comparison was not rerun in this environment: Docker, `pg_ctl`, and local DB URLs are unavailable. No PR was opened to trigger CI because the final canary order's frozen supply prerequisite is unmet and no source adapter/canary is ready.
- No source schedule, production opportunity, projection, Founder state, worker queue, or database row was changed.
- No PR, merge, deployment, browser smoke, or source activation was performed.

## Next admissible step

Use an already captured Workable/Teamtailor payload to create sanitized frozen evidence and rerun all five candidates, if that payload exists in another authorized local artifact. If it does not, obtain a new explicit source-family order before making any additional source request. Do not canary or merge until five candidates and source-diversity requirements are reproducibly proven.
