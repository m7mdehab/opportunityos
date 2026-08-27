# BRIEF-001 — Source Reconnaissance

**Version:** 1.1 — updated for the completed BRIEF-000 foundation
**Supersedes:** BRIEF-001 v1.0. This v1.1 amendment controls wherever it differs below.
**Predecessor:** BRIEF-000 v1.4, PASS at `c355b8e`.
**Project:** OpportunityOS
**Issued to:** Master Development Agent (Claude Code)
**Issued by:** Founder + Co-owner
**Date:** 27 August 2026
**Governing document:** `OpportunityOS_Master_Product_Development_Plan_v0_2.md`
**Brief format:** Master Plan, Appendix I
**Report format:** Master Plan, §38 (Phase Gate Report)

---

## 0. Read this first

Read `docs/STATE.md`, then `AGENTS.md`, then this brief, then accepted ADRs.
Founder prerequisites are none. Repository bootstrap is complete: do not
re-create the foundation, templates, workflows, guards, or governing documents.
The v1.0 bootstrap instruction is withdrawn. This is a reconnaissance-only
phase; return the final report rather than routine implementation questions.

This is a **reconnaissance brief**, not a build brief. It runs *before* Phase 0
and its only job is to replace an assumption with a measurement.

You are operating under the Master Plan's default contract (§13.0): you receive
this brief once, plan and execute it yourself, resolve ordinary engineering
decisions internally, and return **one final report**. Do not come back with
routine implementation questions. Do come back immediately if you hit a hard
gate listed in §9 below.

Everything in the Master Plan's Product Constitution (§2) applies in full,
including to this brief. Nothing here overrides it.

---

## 1. Objective

Measure how much genuinely Egypt-eligible remote opportunity supply exists
right now, per source, across both founder tracks, and produce the evidence
that will determine the Phase 1 source list.

Two questions, answered with numbers and stored fixtures:

1. **Employment track:** of the remote roles currently open on public,
   machine-readable sources, how many are actually open to a candidate
   residing in Egypt?
2. **Independent track:** of the consulting, tender, and project notices on
   public procurement and freelance sources, how many are open to an
   **individual** rather than a registered legal entity?

---

## 2. Why now

Master Plan §41 lists eight moat candidates. The first — knowing which remote
employers really accept candidates from Egypt and MENA — is the only one a
competitor cannot reproduce quickly. It is also completely unvalidated.

Master Plan §16.2 commits Phase 1 to 16 employment source families and 21
independent source families. There is currently no evidence that any of them
supply Egypt-eligible work in useful volume. Building 37 adapters before
measuring is guessing at expensive scale, and §1.3 forbids guessing.

The measurement is cheap. The build is not. Do the cheap thing first.

**This brief requires zero founder setup.** It does not need the Truth Graph,
the Capability Pack, credentials, a VPS, or a domain. It is deliberately
self-unblocking so it can start immediately.

---

## 3. User value

- **founder_employment:** produces a real, current, deduplicated list of remote
  roles the founder is geographically eligible for, usable the same day.
- **founder_independent_work:** establishes whether individual-eligible
  consulting and tender supply exists at all, or whether the ten procurement
  portals in Phase 1 are over-scoped.

---

## 4. Scope — in

1. **Minimal repository bootstrap.** Git repo, `.gitignore`, `README.md`,
   `CLAUDE.md`, and this brief committed at `briefs/BRIEF-001.md`. Commit the
   Master Plan at `docs/MASTER_PLAN.md`. Extract §2 of the Master Plan verbatim
   into `docs/PRODUCT_CONSTITUTION.md`.

2. **A reconnaissance harness** under `recon/`. Python, standard library
   preferred, `requests` acceptable. Quality bar is "correct and legible", not
   production. Each source is an independent module behind one shared
   normalizer signature. The eligibility classifier must be a pure function of
   a normalized record, importable and runnable against synthetic records with
   no network and no fixtures on disk.

3. **Employment sources to fetch** (public, documented, no authentication):
   Himalayas, Jobicy, Remotive, Remote OK, We Work Remotely (RSS),
   Greenhouse Job Board API, Lever Postings API, Ashby Public Job Posting API.

   For the three ATS APIs, probe a watchlist of **at least 25 real companies**.
   Choose them yourself: remote-friendly companies plausibly relevant to a data
   engineering, data science, analytics, or AI engineering candidate. Record the
   list in the report so the founder can correct it.

4. **Independent-track sources to fetch** (public, documented):
   UNGM public notices, World Bank procurement notices, EU TED Search API,
   AfDB procurement RSS, Freelancer.com developer API (sandbox or public
   endpoints only), Saudi Etimad public tender listing (read-only).

5. **Normalization** to a single flat record: source, title, organization,
   location text, url, posted date, description, plus a raw-payload pointer.

6. **Eligibility classification**, deterministic and rule-based. Three verdicts:
   `eligible` / `excluded` / `unclear`. A stated country restriction always
   beats a generic "Remote" or "Anywhere" label — a posting tagged Worldwide
   that requires US work authorization is `excluded`. Record the matched signal
   as the reason for every verdict.

7. **Individual-eligibility classification** for the independent track:
   `individual_ok` / `entity_required` / `unclear`, based on stated supplier,
   registration, turnover, and bond requirements.

8. **Deduplication measurement.** Fingerprint on normalized organization plus
   normalized title with seniority tokens stripped. Report the duplicate rate
   and the cross-source overlap count. Do not tune the fingerprint to hit a
   target; report what it actually finds.

9. **Fixtures.** Every source returning HTTP 200 writes its raw payload to
   `out/fixtures/<source>.json`. These become the contract-test fixtures
   required by Master Plan Appendix D. This is the second reason the brief
   exists — the recon run pays for the Phase 1 test suite.

10. **Source policy records.** `docs/SOURCE_REGISTRY.yaml`, one entry per source
    touched or deliberately skipped, using the schema in Master Plan §32, with
    the access mode you actually observed rather than the one the plan assumed.

11. **The report.** `docs/SOURCE_EVIDENCE.md`, format per §8 below.

---

## 5. Scope — explicitly out

Do not build, install, configure, or scaffold any of the following. Their
absence is a pass condition, not an omission.

- Next.js, React, any front-end, any UI framework, any CSS
- FastAPI, any web server, any HTTP API of our own
- PostgreSQL, SQLite, any database, any ORM, any migration
- Docker, Docker Compose, Caddy, any deployment or hosting
- Auth, sessions, users, workspaces, tenancy
- Playwright or any browser automation
- The Truth Graph, CV parsing, CV generation, proposal generation
- Any LLM API call inside the harness — classification is rules-only, and the
  reason is cost predictability, not capability
- Background workers, job queues, schedulers, cron
- Any agent framework, council implementation, or orchestration runtime
- Any test framework beyond what the harness needs to prove it parses correctly
- Widening `.mirror-allowlist` beyond `recon/**`

If a decision feels like it needs one of these, it is out of scope. Note it in
the report under "next prerequisites" and move on.

---

## 6. Sources that must NOT be fetched

Master Plan §2.3 separates coverage from permission. The following are in the
plan's registry for coverage but are **alert, deep-link, or partnership routes
only**. For each, the deliverable is a documented access route in
`SOURCE_REGISTRY.yaml`, not data:

LinkedIn, Indeed, Glassdoor, WUZZUF, Bayt, Naukrigulf, GulfTalent, Upwork,
Mostaql, Khamsat, Ureed, Contra, Guru, Malt, Toptal, Wellfound.

Record for each: whether a public RSS or email-alert route exists, what the
terms say about automated access, and what the realistic ingestion path would
be. Reading a public terms page to determine this is permitted. Fetching
listings is not.

---

## 7. Preapproved and forbidden external actions

**Preapproved:**
- HTTP GET against the public endpoints named in §4
- HTTP GET against public terms, robots.txt, and API documentation pages
- `git init`, local commits, and pushing to a repository the founder provides

**Forbidden, without exception:**
- Creating any account on any platform
- Any authenticated request, any login, any credential use
- Submitting any application, proposal, bid, quote, or expression of interest
- Contacting any person or organization by any channel
- Any write, POST, PUT, PATCH, or DELETE against an external service
- Spoofing or disguising the user agent — identify the client truthfully
- Retrying past a documented rate limit, or working around 403, 429, CAPTCHA,
  or any anti-bot control
- Ignoring robots.txt

On 403, 429, or a block: stop that source, record the status code and response
in the registry, continue with the others. A blocked source is a finding, not
a failure.

---

## 8. Required deliverables

### v1.1 mirror and data-handling policy

`recon/**` is added to `.mirror-allowlist` so independent review can execute
the classifier. `out/**` is gitignored, never committed, and never mirrored:
it contains third-party listing content. Publish aggregate statistics rather
than source content whenever measuring would require republishing it.

| Path | Content |
|---|---|
| `README.md` | What the repo is, how to run recon |
| `CLAUDE.md` | Working agreement for future sessions, seeded from the Constitution |
| `docs/MASTER_PLAN.md` | The plan, committed unchanged |
| `docs/PRODUCT_CONSTITUTION.md` | Master Plan §2, extracted verbatim |
| `briefs/BRIEF-001.md` | This brief |
| `recon/` | The harness |
| `out/fixtures/*.json` | Raw payloads, one per responding source |
| `out/opportunities.csv` | Normalized, deduplicated, classified rows |
| `docs/SOURCE_REGISTRY.yaml` | One record per source, §32 schema, observed status |
| `docs/SOURCE_EVIDENCE.md` | The report |

### Report structure — `docs/SOURCE_EVIDENCE.md`

Follow Master Plan §38, with these mandatory numbers stated plainly near the top:

1. Total raw records fetched, and per source
2. Unique records after deduplication, and the duplicate rate
3. Cross-source overlap — how many roles appeared on more than one source
4. **Egypt-eligible count and percentage**, total and per source
5. **Unclear percentage** — the share of postings that state no geography at all
6. **Individual-eligible count** on the independent track, per source
7. Source health — status code, latency, record count, or the exact failure
8. The company watchlist used, so the founder can correct it

Then: scope completed, scope deferred, failures and limitations, and exact next
prerequisites. Include a short section titled **"What this changes about the
plan"** — state directly whether the evidence supports or contradicts §16.2's
37-source Phase 1 and §41's moat hypothesis. Contradicting the plan is an
acceptable and expected outcome. Do not soften it.

---

## 9. Hard gates — stop and report

Pause the affected work, continue everything independent, and surface it in the
report:

- Any source that requires an account, key, or registration to read
- Any source whose terms appear to prohibit the access you were about to make
- Any paid API or anything that would incur cost
- Any request to accept terms of service on the founder's behalf
- Any situation where completing the task appears to require one of the
  forbidden actions in §7

---

## 10. Constraints

- **Budget:** no paid APIs, no LLM calls inside the harness, no spend of any
  kind. Your own session cost is the only cost.
- **Time:** complete in one working session. If you cannot, stop, commit what
  works, and report partial results with evidence. Partial and honest beats
  complete and inferred.
- **Concurrency:** the normalizer record shape is the shared contract and is
  serial — define it first. Every source adapter after that is parallel-safe.
  Classification and deduplication are serial, downstream of ingestion.
- **Council:** not required for this brief. No decision here is difficult to
  reverse, touches personal data, or creates an external side effect. Per §13.3,
  do not convene one. If you believe a decision genuinely triggers §13.3, record
  an ADR under `docs/adr/` and proceed.

---

## 11. Acceptance criteria

Machine-checkable. The brief passes when all of these hold:

- [ ] Repository initializes and `recon/` runs end to end on a clean checkout
- [ ] The eligibility classifier is importable and runnable against synthetic
      records with no network and no fixtures on disk
- [ ] At least 6 of 8 employment sources returned parseable data, **or** each
      shortfall has a recorded status code and response body
- [ ] At least 3 of 6 independent sources returned parseable data, **or** each
      shortfall is recorded the same way
- [ ] A fixture file exists for every source that returned HTTP 200
- [ ] Every fetched or skipped source has a `SOURCE_REGISTRY.yaml` entry
- [ ] Every one of the 16 sources in §6 has a documented access route and no
      fetched listing data
- [ ] The classifier ran over 100% of normalized rows without unhandled errors
- [ ] Every classification verdict carries a stated reason
- [ ] `opportunities.csv` opens cleanly and row count matches the report
- [ ] `out/**` appears in `.gitignore`, is committed to neither repository, and
      is absent from the mirror
- [ ] `recon/**` is in `.mirror-allowlist` and present in the mirror
- [ ] No credential, token, or secret appears anywhere in the repository
- [ ] All eight required numbers appear in `SOURCE_EVIDENCE.md`
- [ ] No forbidden action in §7 was taken

---

## 12. Final report only

Return one Phase Gate Report. Do not stream status updates, do not ask which
companies to use, do not ask how to handle a failing source — the answer is
always "record it and continue."

The founder and co-owner will review `SOURCE_EVIDENCE.md` together and issue
BRIEF-002 based on what it says.

```yaml
phase_id: BRIEF-001
objective: measure Egypt-eligible opportunity supply per source, both tracks
why_now: §41 moat hypothesis and §16.2 source count are both unvalidated
final_report_only: true
council_required: false
budget_cap: zero external spend
concurrency: adapters parallel; normalizer contract serial and first
```
