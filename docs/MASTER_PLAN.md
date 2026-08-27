# OpportunityOS Master Product & Development Plan

**Version:** 0.2 - Dual-Track Founder Master Plan  
**Date:** 27 August 2026  
**Status:** Working source of truth for product, engineering, testing, agents, sources, compliance, and phased rollout  
**Immediate objective:** Reach a genuinely useful founder web alpha as early as possible that supports both (1) employment/job acquisition and (2) independent/freelance/consulting/client-opportunity acquisition for the founder. Then improve both tracks continuously while preserving an architecture that can expand into multi-user B2C employment, freelancer/prosumer products, employer talent sourcing, and organization-level B2B client acquisition.

---

## 1. Executive Summary

OpportunityOS is an **autonomous opportunity acquisition platform**. A user or organization provides its professional truth, goals, constraints, and preferences once. The system then performs as much of the repetitive work as legitimately and safely possible: discovery, normalization, verification, eligibility filtering, fit analysis, ranking, evidence selection, document generation, form preparation, workflow tracking, response classification, and escalation.

The system deliberately stops automating where the highest-value human work begins: **conversation, judgment, negotiation, interviewing, persuasion, and mutual fit**.

The product has four primary segments built on the same core engine:

1. **Job Seeker / Employee (B2C):** find legitimate jobs, verify location/work eligibility, rank fit, tailor truthful CVs, prepare or submit applications where permitted, track outcomes, and surface interviews or assessments.
2. **Freelancer / Independent Professional (B2C or prosumer):** find projects, consulting calls, RFPs, tenders, and permitted freelance opportunities; qualify them; prepare evidence-backed proposals; submit or deep-link according to source policy; surface qualified client conversations.
3. **Employer / Hiring Team (B2B):** ingest an open vacancy and hiring requirements; convert them into a structured hiring specification; search an internal consented talent pool, the employer's own applicant data, and authorized external sources; rank candidates; explain fit and gaps; and return a shortlist for human interviews.
4. **Agency / Consultancy / Business (B2B):** ingest the organization's services, capabilities, credentials, target clients, commercial constraints, and exclusions; discover tenders, RFPs, procurement notices, project opportunities, and permitted leads; score bid/no-bid fit; prepare proposals and supporting evidence; track the pipeline; surface qualified commercial conversations.

The common abstraction is not “job.” It is **Opportunity**.

**Founder sequencing rule:** any source or workflow that can legitimately help the founder obtain paid work as an individual—employment, contract, freelance, consulting, or suitable individual-accessible project opportunity—belongs in the founder critical path. Organization-only recruiting and organization-level sales/procurement workflows are later productization layers.

The common user record is not “resume.” It is a **Truth Graph**: structured, provenance-backed facts about a professional or organization that generated text is allowed to use but never contradict or embellish.

### 1.1 Product promise

> **Give us the truth once. Tell us what outcome you want. We handle the tedious opportunity-acquisition work and bring you back when another human is worth talking to.**

### 1.2 Critical build strategy

The system will be architected as a web SaaS from the beginning, but the **first implemented founder product is deliberately dual-track**:

1. **Employment acquisition:** remote/international jobs, contracts, and career opportunities suitable for the founder as an individual candidate.
2. **Independent opportunity acquisition:** freelance projects, consulting assignments, individual-contractor roles, public consultant calls, suitable RFP/RFQ opportunities, and client opportunities that the founder can legitimately pursue as an individual professional or solo operator.

These two tracks share the same Truth Graph, Opportunity model, source framework, ranking engine, artifact-generation system, tracker, response classifier, and qualified-conversation objective. They therefore belong in the founder critical path rather than being built months apart.

Employer-side recruiting, organization-level agency workflows, public multi-user commercialization, billing, and broad marketplace/network functionality come later.

This avoids three mistakes:

- building a disposable personal script that must later be rewritten as SaaS;
- delaying founder value by implementing employer/public SaaS workflows before the founder can use the system; and
- artificially postponing freelance/client acquisition even though it reuses most of the same founder infrastructure and can generate immediate income opportunities.

### 1.3 Core engineering philosophy

- Own the core product and data model.
- Treat external sites as **replaceable source or action adapters**, not as the platform.
- Prefer official APIs, public feeds, first-party employer career pages, licensed datasets, user-authorized imports, and partner integrations.
- Separate **coverage** from **permission**: a source may be useful for discovery while automated submission is prohibited.
- Never make a generated claim that is not supported by stored evidence.
- When uncertain, degrade from automation to human review rather than guessing.
- Every consequential action must be idempotent, traceable, and attributable to a user, source, rule, and agent run.
- No master agent or LLM council may bypass tests, legal gates, source policies, user consent, or human approval boundaries.
- **Autonomous development is the default:** after founder setup and a phase brief, the Master Development Agent plans, delegates, reviews, repairs, tests, documents, and reports the phase without routine founder intervention.
- **Parallel execution is the default:** independent workstreams run concurrently; serial execution requires an explicit dependency, shared-state constraint, or safety/compliance gate.

---

## 2. Product Constitution: Non-Negotiable Rules

These rules are loaded by every development agent, runtime agent, and council member. A phase cannot override them without an explicit founder decision and a recorded Architecture/Product Decision Record (ADR/PDR).

### 2.1 Truthfulness

1. Generated CVs, profiles, proposals, shortlists, application answers, and outbound messages may **select, reorder, summarize, and rewrite** verified facts.
2. They may not invent employers, dates, titles, skills, credentials, achievements, clients, project outcomes, revenue, years of experience, tools, languages, work authorization, or any other factual claim.
3. Every material generated claim must be traceable to one or more `EvidenceClaim` records.
4. Certification states are explicit: `completed`, `in_progress`, `expired`, `planned`. Planned credentials may not be represented as held.
5. If evidence is insufficient, the output must omit the claim or request review.

### 2.2 Human-first automation

Automate the boring work; preserve human judgment.

Humans should normally handle:

- interviews and recruiter calls;
- client discovery calls;
- negotiation;
- salary decisions where policy is not pre-approved;
- legal declarations that are ambiguous;
- unusual work-authorization questions;
- sensitive disclosures;
- final bid strategy for high-value tenders;
- hiring decisions;
- any action where the system's confidence is below the applicable threshold.

### 2.3 Source and platform compliance

1. No scraping or automated interaction merely because it is technically possible.
2. Each adapter has a `SourcePolicy` defining allowed access, attribution, storage, rate limits, automation level, and prohibited actions.
3. LinkedIn, Indeed, Upwork, and similar platforms default to **manual/deep-link/approved-integration only** unless an explicit permitted method is documented.
4. CAPTCHA, MFA, anti-bot controls, or account verification are never bypassed.
5. If a source changes terms or behavior, the adapter can be disabled without affecting the rest of the system.

### 2.4 Privacy and security

1. Multi-tenant isolation is designed from the first database schema, even when the founder is the only user.
2. Sensitive data is minimized and encrypted where appropriate.
3. Every user can eventually inspect, export, correct, and delete their data subject to lawful retention requirements.
4. Employer ranking must not intentionally use protected/sensitive attributes as fit features.
5. Secrets are never committed to source control.
6. Production logs must not contain raw passwords, tokens, CV contents, national IDs, or other unnecessary sensitive data.

### 2.5 Side-effect safety

The following have **zero-tolerance** failure criteria:

- duplicate application to the same opportunity for the same user;
- application submitted when the user/source policy says “review only”;
- auto-answering a Red-class question;
- cross-tenant data leakage;
- unsupported CV claims;
- contacting a person or organization through a prohibited automated channel;
- presenting a candidate to an employer without appropriate data/consent basis.

---

## 3. Product Model and Shared Vocabulary

### 3.1 Actors

- **Professional:** employee, job seeker, contractor, freelancer, consultant.
- **Organization:** employer, agency, consultancy, vendor, client-seeking company.
- **Workspace:** tenant boundary containing users, data, policies, and opportunities.
- **Counterparty:** employer, buyer, client, hiring team, procurement entity, or candidate depending on workflow.

### 3.2 Opportunity types

`Opportunity.type` is extensible and initially supports:

- `employment`
- `contract_role`
- `freelance_project`
- `consulting_assignment`
- `tender`
- `rfp`
- `rfq`
- `client_lead`
- `candidate`

### 3.3 Shared workflow

```text
Profile / Organization Truth Graph
            |
            v
Opportunity Discovery
            |
            v
Source Verification + Provenance
            |
            v
Eligibility / Hard Constraints
            |
            v
Semantic + Evidence Fit
            |
            v
Score + Explanation + Uncertainty
            |
            v
Positioning / Evidence Selection
            |
            v
Artifact or Response Generation
            |
            v
Permitted Action / Human Handoff
            |
            v
Tracking + Response Classification
            |
            v
Qualified Human Conversation
```

### 3.4 North-star outcome

The platform's unifying outcome metric is:

**Qualified human conversations generated per unit of user effort.**

Examples:

- Employment: recruiter screen or interview.
- Freelancer: real client response or discovery call.
- Agency/business: qualified buyer conversation, shortlist invitation, or tender progression.
- Employer: hiring-manager-approved candidate conversation/interview.

Volume alone is not success.

---

## 4. Release Cutlines: Fastest Route to Founder Value

The complete product is large. The build therefore has explicit founder-first cutlines. From the first usable release, the founder gets **both employment acquisition and independent/freelance/client acquisition**.

### Cutline A - Founder Alpha 0: Dual-Track Useful Immediately

The founder can log into the website and use two views powered by one engine:

**Employment track**
- see verified and deduplicated jobs/contracts from multiple legitimate sources;
- understand eligibility and fit;
- generate a fact-locked tailored CV/application package;
- open the canonical employer application;
- track the outcome.

**Independent opportunity track**
- see verified and deduplicated freelance projects, consulting calls, suitable tenders/RFPs/RFQs, contract assignments, and client opportunities from multiple legitimate sources;
- see bid/no-bid qualification and evidence fit;
- generate an evidence-backed proposal/response package;
- open the canonical opportunity/submission page or use an explicitly permitted action path;
- track the outcome.

**No automatic external submission is required for this cutline.** This is intentionally the first usable product so live market learning begins as early as possible.

### Cutline B - Founder Alpha 1: Trusted Discovery Across Both Tracks

Source coverage, company/buyer watchlists, eligibility/qualification precision, legitimacy checks, stale-opportunity verification, compensation/budget normalization, and feedback learning are strong enough that the founder can treat OpportunityOS as the default market view for both employment and independent work.

### Cutline C - Founder Alpha 2: Trusted Tailoring

The Truth Graph and artifact compilers are strong enough that tailored CVs, application answers, proposals, evidence packs, and bid/no-bid explanations rarely need factual correction or structural rewriting.

### Cutline D - Founder Alpha 3: Application and Proposal Assist

The browser/action layer fills deterministic fields and prepares permitted submissions. Green/Yellow/Red policies control employment questions and commercial/bid questions. The founder handles only ambiguous or consequential items.

### Cutline E - Founder Alpha 4: Qualified-Conversation Attention

Inbox/response classification, application/bid tracking, interview/client-response detection, notifications, and analytics reduce routine attention toward the product promise: the founder mainly returns when an employer, recruiter, buyer, or client is worth talking to.

### Cutline F - Private Family Alpha

Multiple invited users can safely maintain separate Truth Graphs, preferences, job/freelance feeds, generated artifacts, and histories. Employment and independent-opportunity modes can be enabled per user.

## 5. Technical Architecture

### 5.1 Architecture decision

Because this is now a web product with eventual multi-user SaaS behavior, the system should use **PostgreSQL rather than SQLite** as the primary database. It remains self-hostable and portable while avoiding a later foundational database migration simply to support concurrency, multi-tenancy, workers, and production reliability.

### 5.2 Recommended owned stack

| Layer | Primary choice | Reason | Dependency posture |
|---|---|---|---|
| Web UI | Next.js + TypeScript | mature app routing, SSR where useful, strong ecosystem | owned source code |
| UI system | shadcn/ui + Tailwind | editable copy-in components, not a visual black box | low lock-in |
| Starting template | Vercel Next.js SaaS Starter, forked | avoids inventing auth/dashboard layout from zero | source copied/forked; Vercel hosting not required |
| API/domain | FastAPI + Python | excellent for data/LLM/browser workloads and typed API | open source |
| Database | PostgreSQL | SaaS-ready, durable, transactional | self-host initially |
| Background work | PostgreSQL-backed job table + workers | avoids Redis/Celery dependency at alpha | owned |
| Browser automation | Playwright | deterministic browser control, uploads, tracing | open source |
| Auth | Auth.js or equivalent self-owned auth layer | avoids proprietary auth lock-in | open source |
| Documents | structured templates + python-docx / HTML renderer + PDF conversion | fact-locked compiled artifacts | owned templates |
| Reverse proxy/TLS | Caddy | simple automatic HTTPS | open source |
| Packaging | Docker + Docker Compose | same stack locally/staging/VPS | portable |
| CI/CD | GitHub Actions initially | convenient; workflow remains portable | replaceable |
| Observability | structured logs + audit tables; OpenTelemetry later | traceability before complexity | standards-based |
| LLM | provider abstraction | model can be replaced | no hard coupling |
| Storage | encrypted local/VPS volume initially; S3-compatible interface later | minimal dependency at alpha | portable |

### 5.3 Front-end starting point

Do **not** ask an LLM to invent the interface from a blank canvas.

Primary base:

1. Fork the **Vercel Next.js SaaS Starter** as a code starting point.
2. Use **shadcn/ui Blocks**, especially dashboard/sidebar/table patterns, as editable building blocks.
3. Remove unneeded Stripe/billing code during personal alpha.
4. Remove or replace Vercel-specific runtime assumptions if they interfere with self-hosting.
5. Treat every imported component as owned code after license review.

Initial pages:

- Sign in / account
- Dashboard
- Opportunities Feed
- Opportunity Detail
- Needs Attention
- Professional Truth Graph
- CV / Generated Artifacts
- Applications / Engagement Pipeline
- Sources / Company Watchlist
- Analytics
- Automation Rules
- Settings / Privacy
- Founder Admin: Agent Runs, Source Health, Evals, Failures

Later workspace modes:

- Professional
- Freelancer
- Employer
- Agency / Business Development

### 5.4 Service boundaries

```text
Web Browser
   |
   v
Next.js Web App
   |
   v
FastAPI Application API
   |---------------------------|
   v                           v
PostgreSQL                 Document Store
   |
   |---- Source Worker
   |---- Match/Eval Worker
   |---- Document Worker
   |---- Browser Action Worker
   |---- Notification Worker
   |---- Agent/LLM Worker
```

A modular monolith is preferred over microservices at the beginning. Separate processes/workers may exist, but the codebase should remain one repository until scale or team boundaries justify separation.

---

## 6. Core Data Model

Every table is tenant-aware from the beginning.

### 6.1 Identity and workspaces

- `User`
- `Workspace`
- `WorkspaceMembership`
- `RolePermission`
- `ConsentRecord`

### 6.2 Truth graph

Professional:

- `ProfessionalProfile`
- `Experience`
- `EvidenceClaim`
- `Achievement`
- `Skill`
- `Credential`
- `Education`
- `Project`
- `PortfolioItem`
- `Language`
- `Preference`
- `ApplicationAnswer`
- `Restriction`

Organization:

- `OrganizationProfile`
- `ServiceOffering`
- `Capability`
- `CaseStudy`
- `ClientReference`
- `IndustryExperience`
- `CommercialConstraint`
- `IdealClientProfile`
- `VendorCredential`

### 6.3 Opportunity and source provenance

- `Opportunity`
- `OpportunitySourceRecord`
- `SourceAdapter`
- `SourcePolicy`
- `SourceHealth`
- `Company`
- `LocationRule`
- `CompensationRange`
- `OpportunityFingerprint`

Every discovered opportunity must retain:

- original source;
- canonical URL if identifiable;
- source record ID;
- retrieval time;
- first-seen and last-verified timestamps;
- raw source hash;
- normalized representation;
- source confidence;
- current availability status.

### 6.4 Intelligence and decisions

- `EligibilityAssessment`
- `FitAssessment`
- `MatchFactor`
- `UncertaintyFlag`
- `GeneratedArtifact`
- `GeneratedClaimReference`
- `QuestionAnswerDecision`
- `AgentRun`
- `DecisionRecord`
- `EvaluationCase`

### 6.5 Engagement and outcomes

- `Engagement`
- `Application`
- `Proposal`
- `Outreach`
- `CandidatePresentation`
- `EngagementEvent`
- `MessageClassification`
- `Interview`
- `Assessment`
- `Offer`
- `Rejection`
- `Outcome`

### 6.6 Employer-specific

- `Vacancy`
- `HiringSpecification`
- `CandidateProfile`
- `CandidateSourceRecord`
- `CandidateMatch`
- `Shortlist`
- `HiringManagerFeedback`

### 6.7 Audit and operations

- `AuditEvent`
- `BackgroundJob`
- `FeatureFlag`
- `SourceFailure`
- `SecurityEvent`
- `DataExportRequest`
- `DeletionRequest`

---

## 7. Source Strategy: Redundancy Without Chaos

### 7.1 Source tiering

**Tier A - First-party / canonical**  
Employer ATS, employer career page, government procurement portal, issuing organization.

**Tier B - Official API/RSS/structured data aggregator**  
Reliable discovery source with documented machine access.

**Tier C - Established board or marketplace with restricted automation**  
Useful coverage, but ingestion/action only through alerts, user forwarding, partnership, approved API, or deep-link workflow.

**Tier D - Unknown aggregator / secondary lead**  
May discover opportunities, but the system must verify against a canonical first-party or high-trust source before recommending or acting.

### 7.2 Source adapter contract

Every adapter must implement:

- `discover()`
- `fetch_detail()`
- `normalize()`
- `canonicalize()`
- `health_check()`
- `policy()`
- `attribution()`
- `rate_limit_state()`

Optional only where permitted:

- `prepare_action()`
- `submit_action()`
- `confirm_action()`

No other part of the platform may rely on source-specific fields.

---

## 8. Employment Job Source Registry

This registry is deliberately broad. “Included” does not mean “scraped.” Each source has an allowed access mode.

### 8.1 Direct ATS and first-party sources - highest priority

| Source | Role | Access strategy | Initial status |
|---|---|---|---|
| Greenhouse Job Board API | direct employer jobs | public GET API; canonical company board | Phase 1 |
| Lever Postings API | direct employer jobs | public postings API | Phase 1 |
| Ashby Job Postings API | direct employer jobs | public job board endpoint | Phase 1 |
| Employer career pages | canonical verification | approved HTTP fetch + structured data / documented page parser | Phase 1-2 |
| Schema.org `JobPosting` JSON-LD | normalization aid | parse structured data on legitimate public company pages | Phase 2 |
| Workable career pages | direct employer jobs | first-party page / approved integration; no assumed generic public API | Phase 2+ |
| Workday career pages | direct employer jobs | company-specific public pages/feeds where permitted | Phase 2+ |

**Design principle:** Maintain a **Company Watchlist**. Known target employers are checked directly, independent of whether an aggregator has indexed them.

### 8.2 API/RSS remote aggregators

| Source | Geography/value | Machine access | Important implementation note |
|---|---|---|---|
| Himalayas | global remote, strong location restrictions | public JSON API | attribution; call server-side; excellent for Egypt/worldwide filtering |
| Jobicy | global remote | public API + RSS | useful secondary feed and category coverage |
| We Work Remotely | global remote | official RSS | attribution/backlink rules |
| Remotive | global remote tech/business | API + RSS | free API may be delayed; attribution/commercial terms must be respected |
| Remote OK | global remote | public feed/API | terms and attribution registry required |
| Adzuna | broad international | authenticated API | rate limits and commercial use terms; enable only under appropriate agreement |

### 8.3 Regional and high-coverage sources

These are valuable for human-facing coverage but **not default scraping targets**.

- WUZZUF - Egypt/MEA jobs and job alerts.
- Bayt - Middle East jobs.
- Naukrigulf - Gulf jobs.
- GulfTalent - Gulf professional jobs.
- LinkedIn Jobs - discovery, alerts, recruiter interaction; no unauthorized bot/scraping workflow.
- Indeed - discovery/alerts/deep links; no unauthorized automated scraping or bulk applying.
- Glassdoor - supplementary discovery/company research subject to terms.

Allowed ingestion patterns can include:

- user-configured email alerts;
- user-forwarded job emails;
- permitted RSS/API;
- browser deep links;
- employer/board partnerships;
- user-authorized imports;
- canonical verification of a job found elsewhere.

### 8.4 Source triangulation

For high-priority jobs, the system should try to answer:

1. Does the canonical employer page still exist?
2. Is the posting still open?
3. Do two independent sources agree on title/company/location?
4. Is remote geography explicitly compatible with the user?
5. Does the apply URL resolve to the employer or a trusted ATS?
6. Is the posting suspiciously old, duplicated, or reposted?

A job may be discovered on Tier C/D but promoted to high confidence after canonical verification.

---

## 9. Freelancer and Consulting Opportunity Source Registry

### 9.1 Marketplaces

| Source | Access posture | Planned use |
|---|---|---|
| Freelancer.com | official developer API and sandbox exist | high-priority integration candidate after API/terms review |
| Upwork | manual/deep-link or specifically approved API only | discovery/assist; no unauthorized proposal bot |
| Mostaql | policy review / partnership / user-assisted flow | MENA freelance coverage |
| Khamsat | policy review / partnership / user-assisted flow | MENA service-market coverage |
| Contra | policy review | supplementary professional/freelance discovery |
| PeoplePerHour | policy review | supplementary source |

### 9.2 Procurement, consulting calls, RFPs and tenders

These are especially valuable for consultants, agencies, and businesses because they represent direct buyer demand.

**Official / first-party sources to support or validate:**

- UAE Ministry of Finance Digital Procurement Platform.
- Saudi Etimad tender portal.
- Egypt General Authority for Government Services / Government Procurement Portal.
- United Nations Global Marketplace (UNGM) public procurement opportunities and developer APIs.
- World Bank business opportunities and procurement notices / public procurement data.
- EBRD Client e-Procurement Portal (ECEPP).
- African Development Bank procurement notices and RSS feeds.
- EU Tenders Electronic Daily (TED) Search API for published procurement notices.
- Individual ministry, authority, university, state-owned enterprise, and large-company procurement pages.
- Donor and development-agency consulting calls where access and reuse are permitted.

### 9.3 Business opportunity ingestion types

The source layer should recognize:

- RFP
- RFQ
- RFI
- Expression of Interest
- Invitation to Bid
- Prequalification
- Call for Individual Consultant
- Framework agreement
- Vendor registration opportunity
- Consulting assignment
- Project subcontracting opportunity

---

## 10. Employer Candidate-Source Strategy

The employer product must **not** assume that “scanning the market” means scraping every public profile on the internet. Candidate sourcing is privacy-, licensing-, and platform-sensitive.

### 10.1 Source priority

1. **OpportunityOS opt-in talent pool** - strongest future network effect.
2. **Employer's own ATS/applicant database** - imported through employer-authorized API, CSV, or connector.
3. **Employer-owned CV/resume files** - with documented lawful basis and retention rules.
4. **Recruiter-referred or invited candidates** - consented workflow.
5. **Authorized commercial talent databases / partners** - contractual integrations.
6. **Public professional evidence for enrichment** - only where lawful and permitted; never a license to invisibly harvest or profile people.

### 10.2 Two separate employer scans

The employer workflow performs two different searches:

**A. Talent search:** find actual candidates from authorized sources.

**B. Market calibration:** scan comparable job postings and market data to understand:

- common titles;
- skill requirements;
- credential patterns;
- geography;
- seniority;
- compensation where public;
- scarcity signals.

The market-calibration scan can use the same job-source engine built for B2C. This is a major shared asset.

---

## 11. Source Legitimacy and Fraud Defense

Every opportunity receives a `SourceConfidence` score independent of `FitScore`.

### 11.1 Signals that increase confidence

- canonical employer/issuer page;
- official ATS domain linked from employer site;
- official government or multilateral procurement portal;
- consistent company identity/domain;
- recent verification;
- valid HTTPS and stable page;
- multiple reputable sources agreeing;
- company has an established web presence;
- apply flow does not request suspicious payments or unrelated sensitive data.

### 11.2 Risk signals

- application asks the candidate to pay money;
- interview only through unusual messaging accounts;
- domain impersonation;
- job absent from employer's canonical page when it should be present;
- unrealistic salary with vague responsibilities;
- crypto/payment requests;
- request for unnecessary identity/bank details before legitimate hiring stage;
- repeated copied listings from unknown aggregators;
- broken or redirected apply endpoint;
- stale posting.

High-risk opportunities are never auto-submitted.

---

## 12. Founder Setup Phase - What Must Be Completed by the Founder

This is the only intentionally founder-heavy phase. The goal is to create enough ground truth, credentials, boundaries, and infrastructure that development agents can execute subsequent work with minimal interruption.

### 12.1 Founder Career Truth Pack - mandatory for Founder Alpha

- [ ] Upload current master CV and any strong historical CV variants.
- [ ] Record exact employer names.
- [ ] Record exact job titles and whether a different market-facing title may be used without misrepresentation.
- [ ] Record exact employment start/end dates.
- [ ] Add responsibilities for each role.
- [ ] Add achievements and metrics, marking whether each metric is verified, approximate, or unavailable.
- [ ] Add technologies/tools actually used, with proficiency/evidence notes.
- [ ] Add projects and portfolio evidence.
- [ ] Add education details.
- [ ] Add languages and realistic proficiency levels.
- [ ] Add every certification with state: completed / in progress / expired / planned.
- [ ] Add credential URL/ID where applicable.
- [ ] Add LinkedIn, GitHub, portfolio, and public professional URLs.
- [ ] Add approved professional summaries or positioning statements if available.
- [ ] Add wording that must never be used because it exaggerates experience.
- [ ] Add gaps/ambiguities that the system must not resolve by guessing.

### 12.1A Founder Independent Professional / Capability Pack - mandatory for Founder Alpha

This is the founder-side equivalent of an agency capability graph and is required from the beginning, not deferred to a later freelancer phase.

- [ ] Define services the founder can legitimately sell or deliver.
- [ ] Define target project/engagement types.
- [ ] Define preferred client industries and excluded industries.
- [ ] Define individual contractor/freelance/consulting positioning.
- [ ] Add portfolio items, work samples, case studies, and evidence links.
- [ ] Add client/project outcomes that are supportable by evidence.
- [ ] Define available capacity and start availability.
- [ ] Define hourly/day/project rate guidance and minimum acceptable economics where desired.
- [ ] Define preferred contract length and engagement model.
- [ ] Define target project size floor/ceiling.
- [ ] Define countries/regions the founder can serve.
- [ ] Define travel/on-site willingness for project work.
- [ ] Define languages usable for delivery/proposals.
- [ ] Define tools/technology/services that may be included in proposals.
- [ ] Define services/claims the system must never represent the founder as providing.
- [ ] Record whether opportunities may be pursued as an individual, contractor, sole operator, or through another legal entity; unresolved legal capacity remains a Red item.

### 12.2 Founder Opportunity Preferences - mandatory for both tracks

Define the initial 3-4 role families. Example structure:

- Primary role family.
- Adjacent role family.
- Stretch role family.
- Explicitly excluded roles.

For each:

- [ ] acceptable titles and title synonyms;
- [ ] seniority range;
- [ ] must-have responsibilities;
- [ ] preferred responsibilities;
- [ ] skills worth emphasizing;
- [ ] skills that are genuine gaps;
- [ ] industries preferred/excluded;
- [ ] employment type;
- [ ] remote / hybrid / relocation preferences;
- [ ] countries/regions allowed;
- [ ] timezone limits;
- [ ] travel willingness;
- [ ] sponsorship/visa rules;
- [ ] salary floor and target where desired;
- [ ] currencies;
- [ ] notice period / start availability;
- [ ] company-size preferences;
- [ ] employer blacklist / industry blacklist;
- [ ] maximum acceptable ambiguity before review.


For independent/freelance/client opportunities also define:

- [ ] acceptable opportunity types: freelance project / contract role / consulting assignment / consultant call / RFP / RFQ / tender / direct client lead;
- [ ] target buyer/client types;
- [ ] required minimum budget/rate where known;
- [ ] maximum proposal/bid effort acceptable before human review;
- [ ] deadline tolerance;
- [ ] preferred delivery model: remote / hybrid / travel / onsite;
- [ ] procurement/vendor-registration constraints;
- [ ] excluded marketplaces/sources;
- [ ] minimum evidence strength before the system recommends bidding;
- [ ] commercial/legal commitments that must always be treated as Red.

### 12.3 Application and Proposal Answer Library - mandatory before action automation

Create approved answers for recurring fields:

- [ ] legal name and contact information;
- [ ] location;
- [ ] work authorization by relevant country;
- [ ] sponsorship needs;
- [ ] relocation willingness;
- [ ] travel willingness;
- [ ] remote/hybrid preference;
- [ ] notice period;
- [ ] salary answer policy;
- [ ] years-of-experience calculation policy;
- [ ] education questions;
- [ ] demographic voluntary-disclosure policy;
- [ ] conflict/non-compete questions;
- [ ] portfolio links;
- [ ] consent statements.

Create a separate **Red Question / Red Commitment list** that the system must never answer or commit to autonomously without a pre-approved deterministic rule. This includes unusual work-authorization declarations, salary/compensation decisions outside policy, exclusivity, warranties, indemnities, binding pricing, legal representations, tender declarations, and any commitment with material legal/commercial effect.

### 12.4 Target Company and Buyer Watchlists - strongly recommended

- [ ] Seed target employers.
- [ ] Identify their career pages/ATS where possible.
- [ ] Assign priority: dream / high / normal / exclude.
- [ ] Add known recruiter/team pages only as manual research references, not automated outreach targets.
- [ ] Seed target clients/buyers, consulting organizations, development institutions, and procurement portals relevant to the founder's services.
- [ ] Add recurring RFP/tender/consultant-call pages where applicable.
- [ ] Assign buyer priority: strategic / high / normal / exclude.

### 12.5 Technical accounts and infrastructure - mandatory

- [ ] Temporary product/project name.
- [ ] Domain or subdomain.
- [ ] DNS provider access.
- [ ] GitHub repository under founder control.
- [ ] VPS/cloud server under founder control for staging/personal alpha.
- [ ] Dedicated application/service email address where practical.
- [ ] Notification destination.
- [ ] Password manager.
- [ ] SSH keys.
- [ ] Database encryption/backups secret material.
- [ ] LLM API key(s), if cloud LLMs are used.
- [ ] Optional Adzuna/app keys for sources that require them.
- [ ] Accounts/API credentials for founder-usable freelance/consulting sources only where official access requires them.
- [ ] Procurement/vendor/consultant portal accounts only where the founder is legitimately eligible and chooses to use them.
- [ ] Backup destination.

### 12.6 Product and automation boundaries - mandatory

Founder explicitly approves:

- [ ] Product Constitution.
- [ ] Which actions may occur silently.
- [ ] Which actions require notification.
- [ ] Which actions require explicit approval.
- [ ] Whether any auto-submit is enabled during early personal alpha (recommended: no).
- [ ] Data retention defaults.
- [ ] Personal data that should never be stored.
- [ ] Maximum LLM/API budget cap.
- [ ] Maximum application/proposal action cap per day/source after automation is enabled.

### 12.7 Gold test data - can be seeded and then expanded through use

Ideal initial set:

- [ ] 30-50 obvious good-fit jobs.
- [ ] 30-50 obvious bad-fit/ineligible jobs.
- [ ] examples of misleading “remote” jobs.
- [ ] examples of duplicate/reposted jobs.
- [ ] examples of jobs that require CV emphasis changes.
- [ ] 10-20 typical application questions.
- [ ] 5-10 difficult/red questions.
- [ ] 20-30 strong-fit freelance/consulting/client opportunities.
- [ ] 20-30 bad-fit or commercially unsuitable independent opportunities.
- [ ] 5-10 legitimate public consultant/tender/RFP examples where an individual could plausibly participate.
- [ ] 5-10 proposal examples or manually written response fragments, if available.

If the founder cannot supply enough examples, Shadow Mode collects them and asks only for fast labels during normal use.

### 12.8 Legal/compliance setup - mandatory before non-founder placement activity

- [ ] Maintain a country compliance matrix.
- [ ] Record Egypt employment-platform/recruitment law sources.
- [ ] Record Egypt personal-data requirements.
- [ ] Obtain qualified Egyptian legal review before commercial employment-placement activity or any workflow that may constitute acting as an electronic employment agency.
- [ ] Obtain country-specific review before commercial expansion into KSA/UAE or other regulated jurisdictions.
- [ ] Decide worker charging/subscription model only after counsel reviews applicable recruitment-fee restrictions.
- [ ] Establish platform-policy registry for every automated source/action.

### 12.9 Agent autonomy setup - mandatory

- [ ] Commit this Master Plan to the repository.
- [ ] Commit the Product Constitution.
- [ ] Commit `SOURCE_REGISTRY.yaml`.
- [ ] Commit `AGENT_PERMISSIONS.yaml`.
- [ ] Commit phase acceptance tests.
- [ ] Create ADR and PDR templates.
- [ ] Enable branch protection.
- [ ] Require CI tests before merge.
- [ ] Define production deployment approval rule.
- [ ] Define destructive database migration approval rule.
- [ ] Define secret/billing/legal escalation rules.
- [ ] Set agent spend and concurrency caps.
- [ ] Define the **Phase Brief Contract**: objective, non-negotiables, allowed resources, risk boundaries, and exit criteria.
- [ ] Define the **No Routine Interruption rule**: after a phase starts, the Master Agent does not ask the founder ordinary implementation questions.
- [ ] Define the **Autonomous Repair Loop**: failed review/test returns to the responsible maker agent automatically until pass, bounded by retry/budget policy.
- [ ] Define the **Parallel Worktree/Branch policy** so independent sub-agents can work concurrently without corrupting shared state.
- [ ] Define the **Final-Report-Only default**: the normal human-visible output of a phase is the final phase gate report, not a stream of development questions or status messages.

**Founder Setup Exit Gate:** all mandatory items above are complete enough that a development Master Agent can receive a phase brief once, create the dependency graph, form the appropriate council, spawn parallel specialist agents, implement, independently review, repair, test, stage, document, and return a final evidence-backed phase report without routine founder intervention.

---

## 13. Autonomous Development Organization

### 13.0 Default operating contract: fully autonomous development

Full development automation is the default operating mode once Phase 0 founder setup is complete. The founder supplies the phase brief and pre-approved boundaries; the Master Development Agent owns execution.

Normal phase behavior:

1. receive the brief once;
2. inspect repository, deployed state, prior reports, policies, and current tests;
3. convert the brief into measurable acceptance criteria;
4. build a dependency DAG and mark every task `parallel_safe`, `serial_dependency`, or `gated`;
5. instantiate the necessary LLM Council roles and obtain independent recommendations for triggered decisions;
6. spawn specialist maker agents in isolated branches/worktrees;
7. run independent checker/QA/security/policy agents against outputs;
8. route defects automatically back to the responsible maker;
9. repeat implementation -> review -> test -> repair until gates pass or bounded failure policy is reached;
10. merge in dependency-safe order;
11. deploy to staging automatically;
12. run phase-level E2E, regression, security, data, and acceptance suites;
13. update ADRs/PDRs/docs/source policies;
14. return one final Phase Gate Report describing what was achieved, evidence, limitations, and next prerequisites.

**No routine founder interruption:** the Master Agent must resolve ordinary engineering/product tradeoffs itself using the brief, Product Constitution, council, and tests. If a truly non-delegable hard gate is encountered (for example a new legal interpretation, a new paid commitment outside budget, a missing private credential only the founder can provide, or an irreversible external action outside pre-authorization), the phase should safely pause that gated branch while continuing all independent work. The exception is recorded in the final report unless progression is literally impossible without the missing input.

**Parallel-first rule:** serial work is not a default convenience. A task is serial only when it depends on an unfinished interface/data contract, mutates shared state that cannot be safely isolated, requires the output of another task, or is blocked by a safety/compliance gate.

### 13.1 Master Development Agent

The Master Development Agent owns orchestration, not omniscience.

Responsibilities:

- load current phase, master plan, constitution, ADRs, backlog, test state, source policies;
- inspect repository and live/staging state;
- decompose the current milestone into a dependency-aware task graph;
- identify decisions requiring council review;
- delegate implementation to specialist sub-agents;
- enforce maker/checker separation;
- ensure every code change includes tests and documentation;
- synthesize QA/security findings;
- merge only when acceptance criteria pass;
- deploy to staging automatically where allowed;
- maintain a live dependency DAG and maximize safe concurrency;
- automatically return failed checks to maker agents for repair;
- publish the **final** phase report only after the phase gate resolves;
- avoid routine founder questions and use pre-approved policies/council judgment instead;
- escalate only genuinely non-delegable hard-gate issues.

### 13.2 Dedicated LLM Council

The council is **instantiated and composed by the Master Agent for each phase/task decision that warrants it**. It is not a chatroom where models converge immediately. Members first reason independently from the same decision packet; routine low-risk implementation does not wait on unnecessary council debate.

Standing members:

1. **Product/Value Advocate** - user value, scope, friction.
2. **Systems Architect** - modularity, data model, portability.
3. **Reliability/QA Engineer** - failure modes, observability, testability.
4. **Security/Privacy Reviewer** - attack surface, secrets, tenant isolation, data minimization.
5. **Legal/Platform Policy Researcher** - flags legal/ToS issues; never substitutes for qualified counsel.
6. **Cost/Operations Reviewer** - operational complexity and spend.
7. **UX/Accessibility Reviewer** - workflow clarity and accessibility.
8. **Red-Team Skeptic** - argues why the proposal will fail.
9. **Domain Specialist** - recruiting, freelance marketplace, procurement, or sales specialist depending on decision.

### 13.3 Council triggers

Council review is required for:

- database/domain model changes that are difficult to reverse;
- authentication/authorization architecture;
- tenant isolation;
- personally identifiable/sensitive data handling;
- new automatic submission/outreach capability;
- use of a new source with unclear policy;
- new platform scraping/access method;
- destructive migrations;
- LLM provider/runtime architecture change;
- candidate ranking methodology;
- monetization that intersects recruitment regulation;
- major deployment topology changes;
- addition of a new market/country compliance pack.

Routine UI fixes and isolated bugs do not need a council.

### 13.4 Council decision protocol

1. Master agent creates a structured **Decision Packet**.
2. Each member independently returns:
   - recommendation;
   - assumptions;
   - major risks;
   - test requirements;
   - rollback strategy;
   - confidence.
3. Master agent exposes disagreements instead of averaging them away.
4. A separate Judge agent scores alternatives against the Product Constitution and current phase objectives.
5. Master agent records the chosen decision in an ADR/PDR.
6. High-risk decisions that require human approval are escalated with the alternatives and evidence, not a vague question.

### 13.5 Specialist sub-agents

- Product Requirements Agent
- Frontend Agent
- Backend/API Agent
- Database/Migrations Agent
- Source Connector Agent
- Matching/Ranking Agent
- Eligibility/Geo Agent
- Resume/Artifact Agent
- Browser Automation Agent
- Email/Notification Agent
- QA/Evaluation Agent
- Security/Privacy Agent
- DevOps/Reliability Agent
- Analytics/Experimentation Agent
- Legal/Policy Research Agent
- Recruitment Domain Agent
- Freelancer/Proposal Domain Agent
- Procurement/RFP Domain Agent
- Employer Sourcing Domain Agent
- Cost Control Agent

### 13.6 Maker/checker and autonomous repair rule

No agent may be the sole approver of its own work. Checker failures are not merely reported: they are routed back to the maker agent with reproducible evidence, and the Master Agent automatically re-runs the relevant review/test suite after repair until the acceptance threshold is met or bounded-failure policy triggers.

Examples:

- Source Agent writes Greenhouse adapter -> QA Agent runs contract fixtures -> Policy Agent verifies source policy -> Master may merge.
- Resume Agent changes tailoring prompt -> Evaluation Agent runs gold CV set -> Truthfulness checker validates claim references -> only then release.
- Browser Agent adds submission support -> QA runs mock/live safe tests -> Security/Policy review -> founder gate if external side effect is newly enabled.

### 13.7 Hard gates that remain outside ordinary autonomous discretion

- legal interpretation or licensing choice;
- changing business model in a regulated market;
- production secrets and billing account ownership;
- destructive production data operation outside tested reversible policy;
- enabling auto-submit on a new source/platform class;
- enabling automated external outreach on a new channel;
- launch to paying users;
- major incident disclosure decisions.

Whenever possible these are resolved **before** a phase begins through founder policy, credentials, budget caps, or legal/compliance decisions so they do not interrupt execution. They are exceptions to the final-report-only default, not routine collaboration points.

---

## 14. Standard Phase Execution Protocol

Every phase/sub-phase uses the same autonomous lifecycle.

1. **Brief ingestion** - load the founder-approved phase brief and immutable constraints.
2. **State inspection** - confirm current build, prior gate evidence, incidents, source health, and deployment state.
3. **Requirements lock** - convert goals into machine-verifiable and evaluator-verifiable acceptance tests.
4. **Risk classification** - data, platform, legal, side-effect, security, cost, reversibility.
5. **Dependency DAG + concurrency plan** - explicitly mark parallel-safe, serial, and gated work.
6. **Council formation if triggered** - members reason independently; Judge compares options; ADR/PDR recorded.
7. **Parallel implementation** - specialist maker agents work in isolated branches/worktrees wherever dependencies permit.
8. **Continuous unit/contract testing** - failures block local completion.
9. **Independent checker pass** - QA/eval/security/policy agents review work they did not author.
10. **Autonomous repair loop** - defects are returned to makers; affected tests/reviews rerun until pass or bounded failure.
11. **Dependency-safe integration** - Master Agent merges only compatible, reviewed work.
12. **Staging deployment** - automatic when the phase policy permits.
13. **Phase E2E/regression/chaos/security tests** - include cross-track regression for employment and independent opportunity workflows.
14. **Automated acceptance/evaluation** - use gold sets and deterministic thresholds; founder acceptance is replaced by stored founder labels/rules wherever possible.
15. **Feature-flag release** - only passed capabilities are enabled.
16. **Telemetry/feedback observation** - runtime smoke/health checks during the phase-defined observation window where required.
17. **Documentation + ADR/PDR/source-policy update.**
18. **Final Phase Gate Report** - the normal human-visible output. It contains completed scope, evidence, failures/limitations, metrics, decisions, and exact next prerequisites.

A phase is not done because code exists. It is done only when its exit gate passes or receives an explicit conditional pass under a documented feature flag.

### 14.1 Parallelization map by phase

| Phase | Default topology | Parallel-safe work | Required serial/gated dependencies |
|---|---|---|---|
| 0 Foundation | Mixed, parallel-first | Founder truth/capability data, web shell, backend skeleton, agent-runtime foundation can progress concurrently after repo bootstrap | Repository/constitution precedes merge rules; auth/tenant schema precedes tenant-dependent UI; secrets/legal inputs are gated |
| 1 Founder Alpha 0 | **Highly parallel** | Employment adapters and independent-opportunity adapters; UI and source adapters; CV and proposal artifact tracks; source contract tests | Adapter contract precedes normalization; normalization precedes final ranking; evidence graph precedes artifact truth checks |
| 2 Trusted Discovery | **Highly parallel** | Additional job sources, procurement/consultant sources, alerts, company/buyer watchlists, source-health monitors, salary/budget normalization | Canonical verification contract must exist before stale/fraud decisions can auto-reject |
| 3 Trusted Tailoring | Parallel after evidence model | CV compiler, proposal compiler, skill/service ontologies, role/opportunity policies, artifact render QA | Atomic evidence/provenance model is the shared prerequisite |
| 4 Action Assist | Parallel with strict gates | Employment browser adapters and permitted freelance/API action adapters; field ontologies; mock harnesses | Side-effect/idempotency controls and mock tests must pass before any live external action is enabled |
| 5 Response/Learning | Parallel | Mail ingestion, response classifiers, notifications, analytics, experiment dashboards | Stable engagement IDs and tracking events are prerequisite |
| 6 Family Alpha | Mixed | onboarding UX, per-user preferences, support/admin, eval cohorts | tenant isolation/security must pass before inviting additional users |
| 7 Employment B2C | Parallel with Phase 8 where legal/product dependencies permit | localization, employment onboarding, MENA rules, pricing experiments | commercial/legal employment gate before public paid launch |
| 8 Freelancer B2C/Prosumer | Parallel with Phase 7 where permitted | freelancer onboarding, proposal policies, marketplace/consultant adapters, pricing experiments | source-specific automation permission and applicable commercial/legal review |
| 9 Employer Hiring B2B | Mostly parallel internally | employer workspace, market calibration, authorized candidate connectors, shortlist UX | lawful candidate-source/consent model and ranking/fairness controls precede live candidate presentation |
| 10 Agency/Business B2B | Mostly parallel internally and potentially parallel with Phase 9 | organization graph, procurement sources, qualification, response workspace | legal/commercial commitment controls precede bid submission/outbound automation |
| 11 Unified Platform | **Serial integration phase after proven wedges** | selected infrastructure scaling tasks may parallelize | requires evidence that at least two segment wedges work independently; network features depend on consent/legal model |

The Master Agent may increase or reduce concurrency dynamically, but any move from parallel to serial must be explained in the phase report as a dependency/safety decision rather than convenience.

# PHASE PLAN

## 15. Phase 0 - Foundation and Founder Setup

**Goal:** establish the SaaS-ready web skeleton, source-of-truth files, agent governance, tests, and environment while completing founder inputs.

### 15.1 Phase 0A - Repository and Product Constitution

Deliverables:

- monorepo structure;
- master plan in repo;
- Product Constitution;
- coding conventions;
- ADR/PDR templates;
- feature-flag conventions;
- agent permission matrix;
- definition of done.

Tests:

- repository bootstraps on a clean machine/container;
- secrets scan is clean;
- lint/test commands are deterministic;
- branch protection/CI policy documented.

### 15.2 Phase 0B - Web template and design system

Deliverables:

- fork/copy Vercel Next.js SaaS Starter;
- shadcn/ui dashboard primitives;
- remove unnecessary billing features;
- establish typography/spacing/forms/tables/dialog standards;
- responsive shell;
- accessibility baseline.

Tests:

- desktop and mobile smoke tests;
- keyboard navigation on main shell;
- no horizontal overflow at target breakpoints;
- basic WCAG-oriented automated accessibility check;
- page-load errors = 0 on core routes.

### 15.3 Phase 0C - Backend, database and environment

Deliverables:

- FastAPI project;
- PostgreSQL schema/migrations;
- tenant-aware base entities;
- DB-backed worker queue;
- structured logging;
- Caddy + Docker Compose deployment;
- staging/personal domain HTTPS;
- backup routine.

Tests:

- migration up/down or documented reversible path;
- backup restore test into clean environment;
- worker retries and dead-letter state;
- idempotent job handling;
- HTTPS/security headers baseline;
- staging health checks.

### 15.4 Phase 0D - Agent execution foundation

Deliverables:

- master agent protocol;
- council schemas;
- tool/permission boundaries;
- traceable agent-run records;
- test-gate integration;
- budget controls.

Tests:

- master agent can take a synthetic issue -> sub-agent -> PR -> QA -> staging without founder intervention;
- a failing test blocks merge;
- a council-trigger decision creates an ADR;
- an unauthorized secret/destructive action is blocked and escalated.

### 15.5 Phase 0E - Founder Truth + Capability Pack ingestion

Deliverables:

- founder career profile schema populated;
- founder independent-professional capability profile populated;
- employment role preferences;
- freelance/consulting/client-opportunity preferences;
- application and proposal answer library;
- employer/company and buyer/source watchlists;
- Red Question / Red Commitment list.

Tests:

- profile completeness report;
- duplicate/conflicting dates flagged;
- certifications represented with correct status;
- all required fields used by CV generation have source evidence or explicit null;
- all material proposal/capability claims have evidence or explicit null;
- pricing/rate/business-capacity fields are marked verified, policy, unknown, or Red rather than guessed.

**Phase 0 Exit Gate:** staging website is reachable; login works; DB backups restore; founder career and capability truth data are usable; agent governance is operational; employment and independent-opportunity source adapters can be added in parallel without architecture work.

---

## 16. Phase 1 - Founder Alpha 0: Dual-Track Discovery to Ready-to-Act

**Goal:** become useful to the founder as early as possible for **both employment and independent income opportunities**.

**Execution topology:** highly parallel. The Master Agent creates separate source-adapter squads for employment and independent opportunities, plus shared normalization, profile UI, scoring, and artifact workstreams. Shared contracts are defined first; adapters then build concurrently.

### 16.1 Phase 1A - Professional Truth + Capability Graph UI

Features:

- import CV and existing professional documents;
- structured review of extracted career facts;
- structured services/capabilities/portfolio view for freelance and consulting work;
- manual correction;
- evidence status and provenance;
- employment preferences UI;
- independent-opportunity preferences UI;
- role-family configuration;
- service/engagement-family configuration;
- “never claim” restrictions;
- Red Question / Red Commitment configuration.

Tests:

- import does not silently overwrite reviewed facts;
- extracted facts require provenance;
- conflicts surfaced;
- edits audit logged;
- proposal-relevant claims are subject to the same truth rules as CV claims;
- pricing/business-capacity unknowns are never hallucinated.

### 16.2 Phase 1B - Founder Source Pack: employment + independent opportunities

All currently known legitimate founder-usable source families are evaluated in Phase 1. A source is not deferred simply because it belongs to freelancing/consulting rather than employment. Parallel Source Connector Agents implement adapters or permitted ingestion methods independently.

**Employment / contract sources:**

1. Greenhouse
2. Lever
3. Ashby
4. Himalayas
5. Jobicy
6. Direct company watchlist / canonical company pages
7. We Work Remotely RSS where current access terms remain suitable
8. Remotive API/RSS where current terms are suitable
9. Remote OK feed/API where current terms are suitable
10. Adzuna API where configured and permitted
11. Structured `Schema.org/JobPosting` extraction from first-party career pages
12. Email/alert ingestion for WUZZUF, Bayt, Naukrigulf, GulfTalent, LinkedIn job alerts, Indeed alerts, and selected company lists instead of prohibited automation
13. Remote Talent (remote.com) job discovery through permitted ingestion/deep links
14. Working Nomads Egypt/remote feeds or permitted alerts
15. Arc Egypt remote employment/contract opportunities through permitted discovery
16. Wellfound startup jobs through policy-reviewed alerts/deep links

**Independent/freelance/consulting/client sources:**

1. Freelancer.com official API/sandbox candidate
2. UNGM procurement and consultant opportunities / developer API where applicable
3. World Bank business opportunities and procurement notices
4. African Development Bank consultant/procurement notices
5. EBRD ECEPP procurement opportunities
6. EU TED Search API for suitable public opportunities
7. Saudi Etimad public tender discovery where the founder is eligible
8. UAE federal Digital Procurement Platform discovery where the founder is eligible
9. Egypt government procurement resources where accessible/permitted
10. first-party consulting/vendor/RFP pages on target organizations
11. user-configured client/buyer/RFP watchlists
12. marketplace/email alerts and deep links for platforms where bots/API action is not permitted
13. public contract/fractional/consultant opportunities discovered through the employment source network when structurally closer to independent work than payroll employment
14. Mostaql Arabic freelance projects through permitted/manual/alert modes
15. Ureed MENA freelance/jobs opportunities through permitted access
16. Contra freelance opportunities through policy-reviewed account/deep-link workflows
17. Guru freelance projects through manual/deep-link discovery unless an approved integration exists
18. Malt freelancer/client opportunities where founder geography/eligibility allows
19. Toptal talent-network opportunities if the founder qualifies/joins
20. Arc freelance/contract opportunities, including Egypt-filterable roles
21. Khamsat as service-market/client-demand intelligence and seller opportunity channel, not treated as a normal project-feed source unless supported by its product behavior

Each source receives one of: `active_adapter`, `alert_ingestion`, `manual_deeplink`, `research_only`, or `disabled_policy` status. Lack of permission for automation does **not** remove the source from discovery coverage if a legitimate alert/deep-link/import route exists.

Tests per adapter/ingestion route:

- contract fixture test;
- pagination/date-window handling where applicable;
- rate-limit behavior;
- malformed response behavior;
- source attribution/provenance;
- canonical URL extraction;
- no duplicate ingestion on rerun;
- source can be disabled without pipeline failure;
- source-policy record exists;
- opportunity type classification is correct on gold fixtures.

### 16.3 Phase 1C - Universal normalization and deduplication

Generate canonical normalized `Opportunity` records across employment, contracts, projects, RFPs, tenders, and consultant calls.

Fingerprint inputs may include:

- canonical organization/employer/buyer domain;
- normalized organization name;
- normalized title/opportunity title;
- opportunity type;
- location/geography;
- source ID;
- canonical/apply/bid URL;
- description/scope similarity;
- posting/publication date;
- closing date/reference number for procurement.

Tests:

- exact duplicate recall target >= 99%;
- near-duplicate/repost detection target >= 95% on gold set initially;
- distinct opportunities at same organization not merged;
- same opportunity across sources links to one canonical opportunity with multiple source records;
- job and project/tender records are not incorrectly merged merely because titles are similar.

### 16.4 Phase 1D - Eligibility and qualification engine

**Employment hard filters:**

- remote geography;
- applicant location restrictions;
- work authorization;
- visa/sponsorship rule when explicit;
- timezone overlap;
- onsite/hybrid requirement;
- employment type;
- seniority hard exclusions;
- required language where explicit.

**Independent-opportunity hard filters:**

- individual/contractor/vendor eligibility;
- geography and delivery-location requirement;
- deadline/closing date;
- required registrations/certifications;
- mandatory legal-entity/turnover/bond constraints;
- minimum budget/rate rule where known;
- service/category fit hard exclusions;
- availability/capacity conflicts;
- prohibited sectors/engagement types;
- bid language requirements.

Decision output:

- Eligible / Qualified
- Ineligible / No-bid
- Uncertain -> review

Tests:

- founder-labeled employment and independent-opportunity gold sets;
- **precision target >= 95%** before any automatic rejection is allowed;
- uncertain language must not be forced into binary decisions;
- explanations cite source fields and profile/capability rules.

### 16.5 Phase 1E - Fit and bid/no-bid scoring v1

Shared hybrid score:

- deterministic hard constraints;
- structured feature score;
- semantic responsibilities/scope score;
- evidence coverage;
- uncertainty penalty.

Employment dimensions:

- responsibility fit;
- core skills;
- experience/seniority;
- role family/title;
- industry/domain;
- remote/location compatibility;
- compensation if known;
- career trajectory preference.

Independent opportunity dimensions:

- service/capability fit;
- scope fit;
- portfolio/case-study evidence;
- rate/budget fit;
- client/buyer quality;
- geography/delivery fit;
- effort/deadline;
- commercial/legal risk;
- probability of a meaningful conversation;
- strategic value.

UI shows score, hard constraints, evidence, uncertainty, and **why**.

Tests:

- top-N precision against founder labels for each track;
- no single keyword dominates score;
- missing data does not equal failure unless truly required;
- rationale references opportunity and Truth/Capability Graph evidence;
- high-effort low-evidence bids are penalized rather than blindly recommended.

### 16.6 Phase 1F - Fact-locked CV and proposal compilers

**Employment artifact:**

- select relevant experiences/achievements;
- reorder skills;
- adapt summary;
- rewrite bullets only within evidence boundaries;
- output DOCX/PDF;
- save artifact version tied to opportunity and evidence IDs.

**Independent-opportunity artifact:**

- select relevant capability evidence, portfolio items, case studies, and experience;
- generate proposal/cover response draft;
- generate scope understanding and clarification questions;
- create work-plan outline where appropriate;
- create compliance/required-document checklist for formal opportunities;
- produce attachment/evidence recommendations;
- never invent client history, rates, availability, deliverables, guarantees, or legal status.

Tests:

- unsupported factual claims = **0** across CVs and proposals;
- certification status errors = **0**;
- employment date/title changes outside approved aliases = **0**;
- fabricated client/project/case-study claims = **0**;
- text extraction succeeds from generated documents;
- render regression set has no clipped/overlapping text;
- proposal claims map to evidence IDs;
- unresolved commercial commitments remain visibly unresolved/Red.

### 16.7 Phase 1G - Action handoff and universal tracker

Features:

- “Open canonical application” for employment;
- “Open canonical opportunity / submit page” for independent work;
- artifact download/open actions;
- mark Applied / Proposal Submitted / Bid Submitted / Skip / Save / No-bid;
- feedback: Great Match / Maybe / Bad Match / Wrong Eligibility / Duplicate / Scam Concern / Commercially Poor / Wrong Scope;
- engagement history and source provenance.

Tests:

- correct canonical URL;
- same opportunity cannot create a duplicate action without explicit override;
- state survives refresh/redeploy;
- feedback updates evaluation datasets;
- job and client opportunity histories remain distinct but comparable.

### 16.8 Phase 1H - Founder dual-track daily workspace

Dashboard must expose, at minimum:

- best employment opportunities today;
- best freelance/consulting/client opportunities today;
- reasons for qualification;
- artifacts ready;
- actions completed;
- actions requiring founder attention;
- source health summary;
- recent recruiter/client responses once available.

**Phase 1 Exit Gate / First Usable Founder Product:** the founder can use OpportunityOS daily to replace a substantial amount of manual job-board **and freelance/client-opportunity** browsing, obtain ranked/verified opportunities from multiple independent sources, generate truthful CVs or evidence-backed proposals, follow canonical action paths, and track both employment and independent income pursuits from one web application.

## 17. Phase 2 - Founder Alpha 1: Source Expansion, Verification and Trust

**Goal:** make both employment and independent-opportunity discovery broad, verified, and resilient enough to become the founder's default market view.

### 17.1 Phase 2A - Expand machine-readable sources

Add/validate:

- We Work Remotely RSS
- Remotive API/RSS
- Remote OK feed/API
- Adzuna API under appropriate terms/key
- more company ATS boards
- structured Schema.org JobPosting extraction
- any Founder Source Pack item that remained `research_only` in Phase 1 but can now graduate through an official feed, alert, partnership, or stable permitted adapter

### 17.2 Phase 2B - Regional, marketplace, buyer and alert ingestion

Build an **Email/Alert Ingestion Adapter** so valuable boards do not need scraping.

Sources can include:

- WUZZUF alerts;
- Bayt alerts;
- Naukrigulf alerts;
- GulfTalent alerts;
- LinkedIn job alerts;
- Indeed alerts;
- selected company mailing lists;
- permitted marketplace alerts;
- buyer/procurement newsletters;
- consulting-call/RFP alert lists.

The parser extracts candidate opportunity records and then verifies canonical links where possible.

### 17.3 Phase 2C - Company and Buyer Watchlist automation

- ATS detection;
- source health per company;
- priority polling;
- missing-company/buyer-source alert;
- newly opened role notification;
- newly published project/RFP/consultant-call notification;
- recurring procurement-page monitoring through permitted methods.

### 17.4 Phase 2D - Stale-job and canonical verification

Before a high-effort CV or submission:

- re-check availability;
- confirm canonical URL;
- compare last retrieved content hash;
- detect closed/404/expired pages;
- downgrade stale aggregator-only jobs.

### 17.5 Phase 2E - Fraud/scam risk model

Combine deterministic indicators with cautious LLM review. Scam score never replaces canonical verification.

### 17.6 Phase 2F - Salary and location normalization

- currencies;
- salary, hourly/day/project budget normalization;
- annual/monthly/hourly normalization;
- gross vs unknown;
- location taxonomy;
- country/region/timezone mapping;
- remote scopes: worldwide, EMEA, MENA, country-only, time-zone constrained, unclear.

### 17.7 Phase 2G - Source health and graceful degradation

Dashboard:

- last successful fetch;
- error rate;
- response latency;
- rate-limit state;
- records/day;
- duplicate ratio;
- canonical verification rate.

Chaos tests:

- turn each source off individually;
- simulate rate limit;
- simulate schema change;
- simulate timeout;
- verify remaining feed still functions.

**Phase 2 Exit Gate:** no single job board, marketplace, procurement portal, or aggregator is necessary for useful founder coverage; every surfaced opportunity has provenance; source failures degrade gracefully; top employment and independent-opportunity matches are predominantly judged relevant by founder.

---

## 18. Phase 3 - Founder Alpha 2: Advanced Tailoring and Truth Engine

**Goal:** make generated employment and client-acquisition material trustworthy enough that manual rewriting becomes exceptional.

### 18.1 Phase 3A - Atomic evidence bank

Break experience into evidence-backed atomic units:

- action;
- context;
- tools;
- domain;
- scale;
- outcome;
- confidence;
- verification source.

### 18.2 Phase 3B - Skill ontology and role-family modules

Map synonyms and context:

- skill canonical name;
- aliases;
- evidence strength;
- last-used date;
- role relevance;
- prohibited overclaim transformations.

### 18.3 Phase 3C - Resume compiler

Instead of editing a master document destructively:

```text
Truth Graph + Job Spec + CV Policy + Template -> New CV Artifact
```

Templates are versioned and deterministic.

### 18.3A Phase 3C2 - Proposal / Opportunity Response Compiler

Compile from structured truth rather than free-writing from scratch:

```text
Truth + Capability Graph + Opportunity Spec + Proposal Policy + Evidence Pack -> New Proposal Artifact
```

Support lightweight freelance proposals, consultant expressions of interest, cover responses, capability statements, and structured RFP response scaffolds. Formal high-value legal/commercial documents remain gated.

Tests:

- claim-to-evidence coverage = 100% for material factual claims;
- no fabricated client/project results;
- required fields/checklists detected from gold opportunities;
- unresolved commitments remain Red;
- proposal relevance judged against founder gold set.

### 18.4 Phase 3D - Role-family CV policy

Each role family defines:

- summary positioning;
- preferred experience ordering;
- skill clusters;
- credential visibility;
- project inclusion;
- bullet density;
- maximum page count;
- prohibited exaggeration.

### 18.5 Phase 3E - ATS/readability regression suite

Automated checks:

- text extraction;
- heading detection;
- dates/employers present;
- no accidental images-as-text;
- no missing glyphs;
- contact information correct;
- PDF and DOCX content parity;
- no hidden white text/keyword stuffing.

### 18.6 Phase 3F - Application and proposal answer generation

Only for narrative questions where policy permits. Generated answers must cite truth-graph evidence internally.

**Phase 3 Exit Gate:** unsupported claim count remains zero over both employment and independent-opportunity gold sets; most generated CVs and proposal packages require no factual correction; ATS/document extraction and render tests pass; every material artifact claim has full provenance.

---

## 19. Phase 4 - Founder Alpha 3: Application, Proposal and Controlled Action Automation

**Goal:** remove repetitive form work without introducing uncontrolled external side effects.

### 19.1 Phase 4A - Browser application framework

Playwright worker supports:

- open URL;
- detect form/ATS adapter;
- upload generated CV;
- fill known fields;
- save trace/screenshots where appropriate;
- detect blockers;
- pause safely.

### 19.2 Phase 4B - Field ontology

Canonical fields:

- identity;
- contact;
- address/location;
- education;
- employment;
- links;
- work authorization;
- sponsorship;
- compensation;
- demographic voluntary questions;
- custom narrative.

### 19.3 Phase 4C - Green / Yellow / Red question policy

**Green:** deterministic approved answer; auto-fill.

Examples: name, email, phone, LinkedIn, portfolio, confirmed location.

**Yellow:** answer is automatic only if an explicit user policy exists.

Examples: willingness to travel, relocation, remote preference, standard sponsorship response.

**Red:** always pause unless an exact deterministic pre-approved rule is explicitly stored.

Examples: unusual legal declarations, nuanced salary request, security clearance, conflicts, long motivation essay, ambiguous sponsorship wording, anything sensitive or uncertain.

### 19.4 Phase 4D - Mock ATS test harness

Before using external applications, create local forms that emulate:

- Greenhouse-like;
- Lever-like;
- Ashby-like;
- generic multi-step form;
- file upload;
- validation errors;
- dynamic questions;
- save/resume;
- CAPTCHA placeholder that must cause stop.

### 19.5 Phase 4E - Assisted live mode

System fills but does not submit. Founder reviews the completed page.

Required telemetry:

- fields found;
- fields filled;
- unknown fields;
- answer source;
- confidence;
- manual edits.

### 19.6 Phase 4F - Adapter-specific controlled submit

Only a specific ATS/form adapter may graduate to automatic submit after:

- policy/legal access is acceptable;
- assisted-mode test history is clean;
- unknown question handling is safe;
- idempotency is proven;
- confirmation receipt detection works;
- duplicate-submit prevention works;
- founder explicitly enables it.

### 19.6A Phase 4F2 - Independent-opportunity action adapters

Implement source-specific action modes:

- official API explicitly permits bid/proposal action -> controlled adapter candidate;
- authenticated portal allows user-driven browser preparation -> prepare/assist mode;
- platform prohibits automation -> proposal prepared + deep-link/manual submission only;
- formal tender/RFP -> package preparation only unless a later explicit legal/commercial approval policy permits more.

Tests:

- no prohibited platform action;
- no binding price/legal commitment without approved rule;
- duplicate bid/proposal prevented;
- file/attachment selection verified;
- mock/sandbox environment preferred before live side effects.

### 19.7 Phase 4G - Side-effect controls

Every submission uses an idempotency key such as:

`workspace + candidate + canonical_opportunity + action_type`

System stores:

- before-state;
- form answers;
- CV artifact ID;
- submit time;
- confirmation evidence;
- browser trace;
- outcome.

**Phase 4 zero-tolerance tests:**

- accidental submit in assisted mode = 0;
- duplicate submission = 0;
- Red-question auto-answer = 0;
- CAPTCHA/MFA bypass attempt = 0;
- CV mismatch/wrong user upload = 0.

**Phase 4 Exit Gate:** supported employment applications and permitted independent-opportunity submissions can be prepared with minimal founder work; any automatic external action is limited to individually validated adapters, respects source-specific policy, remains idempotent, and can be disabled globally instantly.

---

## 20. Phase 5 - Founder Alpha 4: Inbox, Interview/Client Response Detection and Learning Loop

**Goal:** reduce founder attention after submission and learn which behaviors actually produce outcomes.

### 20.1 Phase 5A - Mail ingestion

Prefer user-authorized Gmail/IMAP/API integration rather than forwarding passwords.

Classify:

**Employment:**
- application confirmation;
- rejection;
- recruiter outreach;
- assessment;
- interview scheduling;
- offer;
- request for information.

**Independent/client work:**
- proposal/bid confirmation;
- client/buyer human response;
- clarification request;
- shortlist/invitation;
- discovery-call or meeting request;
- proposal rejection;
- award/win/contract-progress signal;
- procurement amendment/deadline change where relevant.

**Noise:**
- irrelevant marketing;
- generic platform notifications with no action value.

### 20.2 Phase 5B - Priority notifications for employment and client work

High priority:

- recruiter or client/buyer human response;
- interview or discovery call;
- assessment/clarification with deadline;
- offer, shortlist, invitation, award, or contract-progress signal;
- request requiring reply.

Low priority:

- confirmation;
- generic rejection;
- non-actionable platform notice;
- marketing.

### 20.3 Phase 5C - Automatic employment and client pipeline updates

Email evidence updates opportunity/application state without requiring founder bookkeeping.

### 20.4 Phase 5D - Dual-track analytics and optimization

Track conversion by:

- source;
- company/buyer type;
- role family or service/opportunity family;
- fit/bid-score band;
- eligibility/qualification confidence;
- CV/proposal template and policy version;
- skill/capability emphasis;
- application/proposal age;
- compensation/budget/rate band where known;
- opportunity type;
- proposal effort;
- recruiter/client response and qualified-conversation outcome.

### 20.5 Phase 5E - Experiment governance

Experiments may change ranking or wording, but never truthfulness rules. Avoid deceptive A/B testing or uncontrolled external volume.

**Email evaluation target:** curated interview/recruiter/assessment gold-set recall should be effectively 100%; false positives are preferable to silently missing an interview.

**Phase 5 Exit Gate:** routine employment and client-work confirmations/rejections require almost no founder work; recruiter, interview, client, buyer, clarification, shortlist, and discovery-call signals are reliably surfaced; analytics identify which sources, opportunity families, CV strategies, and proposal strategies actually create qualified conversations.

---

## 21. Phase 6 - Private Family Alpha: Multi-Tenant Dual-Track Proof

**Goal:** determine whether the dual-track product works for people other than the founder and prove tenant/security boundaries before broader B2C productization.

### 21.1 Legal gate before behavior expansion

Before the system automatically places/applies for other people, obtain legal advice on whether the specific workflow triggers electronic employment/recruitment licensing obligations. If unclear, family alpha runs in **assistive mode**: discovery, ranking, CV tailoring, form preparation, and human final submission.

### 21.2 Multi-user onboarding

- invitation;
- consent;
- CV import;
- truth-graph review;
- role preferences;
- application answer policy;
- source preferences;
- automation level.

### 21.3 Tenant isolation

Tests include:

- API authorization;
- direct object ID manipulation;
- file/document access;
- background worker scoping;
- search indexes;
- logs;
- backups;
- admin tools.

**Cross-tenant leakage tolerance: 0.**

### 21.4 Family alpha cohort

Use a small variety of profiles rather than only similar professions:

- experienced professional;
- early-career candidate;
- different industry;
- different location/remote constraints;
- optionally bilingual Arabic/English profile.

### 21.5 Family alpha success criteria

- independent onboarding completion;
- minimal founder support;
- good-match precision meets threshold across users;
- no factual CV errors;
- no tenant leakage;
- users understand why a match is recommended;
- users can correct profile truth easily;
- manual intervention rate measured.

**Phase 6 Exit Gate:** product demonstrates repeatability beyond the founder and provides evidence about which user segments benefit most.

---

## 22. Phase 7 - Employment B2C Beta

**Goal:** turn the proven personal/family employment workflow into a self-service regional product, only after legal/compliance gates are satisfied.

### 22.1 Arabic/English localization

- interface localization;
- Arabic/English job normalization;
- Arabic/English professional truth fields;
- bilingual CV/presentation policies;
- RTL testing;
- language-specific evaluation sets.

### 22.2 MENA employment intelligence

- Egypt eligibility logic;
- GCC relocation/sponsorship markers;
- EMEA/worldwide remote classification;
- time-zone compatibility;
- country-specific notice/contractor vocabulary;
- salary/currency normalization.

### 22.3 Self-service controls

Users must see and control:

- automation level;
- sources;
- salary/location rules;
- blacklist;
- evidence truth;
- application answer rules;
- data export/deletion;
- activity log.

### 22.4 Commercialization gate

Before charging or public launch:

- Egyptian employment/recruitment licensing review;
- personal-data compliance review;
- terms/privacy policy;
- worker-fee/subscription legality review;
- support/complaint workflow;
- incident process;
- security review;
- source commercial-use review.

### 22.5 Outcome-based product metrics

Do not market “300 applications” as the primary value.

Measure:

- eligible-match precision;
- quality applications/user;
- recruiter response rate;
- interview rate;
- user interventions per application;
- time saved;
- application-to-qualified-conversation conversion.

**Phase 7 Exit Gate:** legally deployable, secure, self-service employment product with demonstrated interview generation and explainable automation.

---

## 23. Phase 8 - Freelancer / Independent Professional B2C & Prosumer Productization

**Goal:** productize, generalize, localize, and commercialize the independent-opportunity functionality that already exists for the founder from Phase 1 onward. This phase is **not** the first implementation of freelancer/client acquisition.

**Execution topology:** may run in parallel with Phase 7 Employment B2C after Phase 6 multi-tenant isolation is proven, provided applicable legal/platform reviews are independent and source adapters are already stable.

### 23.1 Multi-user Capability Graph onboarding

Generalize the founder capability model for different professions:

- services offered;
- rates/pricing rules;
- availability/capacity;
- portfolio/case studies;
- client industries;
- engagement size;
- contract preferences;
- geographical restrictions;
- evidence and references;
- proposal policy;
- exclusions.

### 23.2 Source personalization and policy-safe discovery

Expose per-user source selection across already validated source adapters plus newly approved sources. Discovery may include:

- official marketplace APIs/feeds;
- public consultant calls;
- procurement/RFP/RFQ sources;
- direct buyer/organization pages;
- alert ingestion;
- deep-link/manual-only sources where automation is prohibited.

### 23.3 Generalized bid/no-bid models

Adapt scoring by profession/engagement type while preserving explainability:

- capability fit;
- budget/rate fit;
- evidence strength;
- competition/effort estimate;
- geography;
- deadline;
- commercial risk;
- client quality;
- proposal requirements;
- probability of meaningful conversation.

### 23.4 Proposal compiler templates by opportunity type

Productize templates for:

- lightweight freelance proposals;
- consultant applications/EOIs;
- capability responses;
- RFP/RFQ response scaffolds;
- supporting evidence/case-study packs;
- work plans and clarifications;
- compliance matrices.

Never invent portfolio work, clients, results, rates, legal status, or capacity.

### 23.5 Self-service action controls

- user-specific Green/Yellow/Red commercial rules;
- source-specific submission permissions;
- manual/deep-link mode where policy requires;
- explicit review for high-value legal/commercial commitments;
- activity caps and anti-spam rules.

### 23.6 Commercialization and legal gate

Before charging or broadly automating across marketplaces/countries:

- confirm source terms/commercial API rights;
- confirm applicable intermediary/agency/freelance-service regulation;
- privacy/data review;
- pricing model validation;
- support/complaint process.

### 23.7 Freelancer/prosumer metrics

- relevant opportunities surfaced;
- proposal/bid precision;
- qualified responses;
- discovery calls;
- won work;
- revenue attributed;
- proposal effort saved;
- user interventions per qualified conversation.

**Phase 8 Exit Gate:** the already-proven founder independent-opportunity engine works safely for multiple external professionals with strong source policy compliance, self-service onboarding, and demonstrated client-conversation generation.

## 24. Phase 9 - Employer / B2B Hiring Product

**Goal:** provide employers with a high-value counterpart: requirements in, explainable qualified shortlist out.

### 24.1 Employer workspace

Organization creates:

- company profile;
- hiring team;
- allowed data sources;
- vacancy;
- compensation range;
- location/remote policy;
- seniority;
- must-haves;
- nice-to-haves;
- deal-breakers;
- required credentials;
- target start date;
- interview process.

### 24.2 Hiring Specification Compiler

Convert messy JD/intake into structured `HiringSpecification`:

- outcomes/responsibilities;
- required skills;
- inferred-but-not-confirmed skills clearly separated;
- minimum experience;
- credentials;
- language;
- location/work authorization;
- compensation;
- priority weights;
- questions that require hiring-manager clarification.

### 24.3 Market calibration scan

Use the employment job-source engine to scan comparable current roles and produce:

- common title variants;
- recurring skill combinations;
- experience expectations;
- location patterns;
- salary ranges where legitimately available;
- possible unrealistic requirements;
- scarcity indicators.

This is advisory, not a substitute for the employer's actual requirement.

### 24.4 Candidate discovery

Search only authorized sources:

- OpportunityOS consented pool;
- employer ATS/applicant database;
- employer-provided CV corpus;
- permitted recruitment partner/database integrations;
- referral/import workflows.

### 24.5 Candidate ranking

Output per candidate:

- overall fit;
- must-have pass/fail;
- evidence supporting each match;
- material gaps;
- uncertainty;
- location/work-eligibility status;
- compensation alignment if known/consented;
- recommended interview topics;
- source/provenance.

### 24.6 Shortlist product

Employer receives:

- shortlist;
- notes explaining search strategy;
- excluded-candidate categories in aggregate;
- talent-supply observations;
- recommended requirement adjustments if the search is too narrow;
- interview guide.

### 24.7 Fairness/privacy controls

- no protected/sensitive attributes in ranking features;
- optional anonymized early review;
- explainable scoring;
- human hiring decision required;
- audit trail of rank factors;
- candidate consent/lawful-basis records;
- retention limits.

### 24.8 Employer evaluation

Gold set uses recruiter/hiring-manager labels.

Metrics:

- precision@5 / precision@10;
- must-have false positive rate;
- shortlist acceptance rate;
- interview rate from shortlist;
- time-to-shortlist;
- diversity/fairness monitoring where legally appropriate and privacy-preserving;
- explanation usefulness.

**Phase 9 Exit Gate:** employers consistently judge returned candidates as worth human review, and every candidate presentation is lawful, authorized, explainable, and auditable.

---

## 25. Phase 10 - Agency / Business Client Acquisition B2B Productization

**Goal:** extend the founder's already-proven independent/client-opportunity engine into a true organization-level B2B product for agencies, consultancies, vendors, and service businesses with teams, supplier qualifications, complex bids, and commercial workflows.

### 25.1 Organization Capability Graph

Capture:

- services;
- sectors;
- geographies;
- case studies;
- certifications;
- delivery capacity;
- team skills;
- project size floor/ceiling;
- commercial model;
- preferred client type;
- exclusions;
- compliance registrations;
- vendor registrations;
- languages;
- references.

### 25.2 Buyer opportunity discovery

Priority official sources:

- UAE federal procurement;
- Saudi Etimad;
- Egypt government procurement sources;
- UNGM;
- World Bank;
- EBRD;
- AfDB;
- EU TED;
- specific target-company procurement/RFP pages;
- donor/development programs;
- industry-specific approved sources.

### 25.3 Qualification engine

Hard filters:

- geographic eligibility;
- supplier registration;
- legal entity requirements;
- minimum turnover/bond requirements;
- certifications;
- deadline;
- project size;
- excluded sectors;
- bid language.

Fit scoring:

- service fit;
- evidence/case-study fit;
- client/industry fit;
- delivery capacity;
- strategic value;
- bid effort;
- win likelihood proxy;
- margin potential if inputs exist.

### 25.4 RFP/Tender response workspace

Generate structured assistance:

- opportunity summary;
- compliance matrix;
- mandatory documents;
- questions/clarifications;
- evidence mapping;
- proposal outline;
- work plan;
- team CV selection;
- risks;
- deadline calendar;
- missing-information checklist.

High-value bids remain human-approved.

### 25.5 Permitted outbound business development

Where legally and platform-policy permitted:

- identify target organizations;
- produce account brief;
- identify relevant public business trigger;
- draft personalized outreach;
- send only through approved channels and configured rate/consent policy.

No spam engine.

### 25.6 B2B acquisition metrics

- qualified opportunity rate;
- bid/no-bid accuracy;
- proposals submitted;
- shortlist/invitation rate;
- qualified buyer calls;
- wins;
- revenue pipeline created;
- user effort per qualified conversation.

**Phase 10 Exit Gate:** system demonstrably reduces business-development effort while increasing qualified opportunities, with rigorous proposal truth and source compliance.

---

## 26. Phase 11 - Unified Opportunity Platform and Regional Scale

**Goal:** exploit shared data/engine/network effects after each wedge works independently.

### 26.1 Unified workspace model

A user/organization can activate one or more modes:

- Find Work
- Find Projects
- Hire Talent
- Find Clients

### 26.2 Permissioned marketplace/network effects

Potential future advantages:

- job seekers opt into employer discovery;
- freelancers opt into project discovery;
- employers can access consented relevant talent;
- businesses can publish opportunities;
- evidence-backed identity reduces duplicate onboarding.

This is not required for early product-market fit.

### 26.3 Country compliance packs

Each country launch has:

- recruitment/employment regulation;
- personal data/privacy;
- consumer protection;
- e-commerce/subscription rules;
- permitted worker/employer charging model;
- platform terms;
- hosting/data residency implications where relevant;
- local language/support requirements.

### 26.4 Scale architecture only when justified

Potential later upgrades:

- managed Postgres or HA cluster;
- object storage;
- dedicated queues;
- horizontal workers;
- CDN;
- OpenTelemetry collector;
- enterprise SSO;
- SIEM;
- SOC 2 / ISO 27001 preparation;
- formal disaster-recovery environment.

Do not pay this complexity tax before usage demands it.

---

## 27. Global Testing and Evaluation Framework

Every phase must use the relevant layers below.

### 27.1 Layer 1 - Unit tests

Deterministic functions:

- normalization;
- eligibility rules;
- scoring arithmetic;
- currency/location utilities;
- idempotency;
- permissions;
- document data binding.

### 27.2 Layer 2 - Source contract tests

Each source has recorded fixtures plus live health tests where appropriate.

Validate:

- schema;
- pagination;
- rate limits;
- attribution;
- content hashes;
- error handling;
- canonical links;
- disabled-source behavior.

### 27.3 Layer 3 - Integration tests

Examples:

- ingest -> normalize -> dedupe -> rank;
- profile -> CV generation -> artifact storage;
- capability graph -> opportunity -> proposal generation -> artifact storage;
- employment browser worker -> form state -> engagement record;
- permitted proposal/bid action adapter -> action state -> engagement record;
- email -> employment/client classification -> pipeline update.

### 27.4 Layer 4 - Golden-set LLM evaluations

LLM behavior is versioned and evaluated, not trusted by intuition.

Gold sets include:

- good/bad job matches;
- eligibility ambiguity;
- CV bullet rewrites;
- unsupported-claim traps;
- duplicate descriptions;
- scam indicators;
- application questions;
- email classifications;
- employer candidate matches;
- freelance/consulting opportunity matches;
- proposal-generation claim traps;
- tender/RFP/consultant-call bid/no-bid examples;
- client-response email classifications.

Every LLM result is structured and schema-validated.

### 27.5 Layer 5 - End-to-end browser tests

Test complete user workflows with a real browser on staging.

### 27.6 Layer 6 - Security/privacy tests

At minimum:

- authentication;
- authorization;
- tenant ID tampering;
- CSRF/XSS/injection;
- file upload validation;
- secret leakage;
- SSRF risks in source fetchers;
- dependency/supply-chain scanning;
- logging redaction;
- abuse/rate limits.

Use OWASP Top 10:2025 as a baseline awareness framework and add more complete verification controls as the product matures.

### 27.7 Layer 7 - Human acceptance and real-use labels

Humans label whether the output is useful and correct during product use and evaluation. These labels are inputs to gold sets; they are **not routine development interruptions** during an autonomous phase.

Examples:

- founder match label;
- founder CV factual review;
- family user acceptance;
- recruiter/hiring-manager shortlist review;
- freelancer proposal usefulness;
- business bid/no-bid review.

### 27.8 Layer 8 - Outcome metrics

The strongest test is market response:

- recruiter responses;
- interviews;
- client responses;
- discovery calls;
- shortlisted bids;
- accepted employer shortlists;
- offers/wins.

### 27.9 Layer 9 - Chaos and degradation testing

- source unavailable;
- LLM unavailable;
- browser worker crashes mid-action;
- DB connection interruption;
- expired credential;
- email connector unavailable;
- malformed CV;
- changed ATS form.

System must fail closed on consequential actions and recover without duplication.

---

## 28. Universal Quality Gates

These gates apply regardless of phase.

| Metric | Gate |
|---|---|
| Unsupported generated factual claims | **0 tolerated** |
| Cross-tenant data leak | **0 tolerated** |
| Duplicate external application/action | **0 tolerated** |
| Red-class question auto-answered without rule | **0 tolerated** |
| CAPTCHA/MFA bypass behavior | **0 tolerated** |
| Opportunity provenance | **100% required** |
| Generated artifact -> evidence trace | **100% for material claims** |
| Side-effect action audit trace | **100% required** |
| Founder employment eligibility precision before auto-reject | target **>=95%**, uncertainty routes to review |
| Founder independent-opportunity qualification precision before auto-no-bid | target **>=95%**, uncertainty routes to review |
| Fabricated client/project/case-study claims | **0 tolerated** |
| Exact duplicate detection | target **>=99%** |
| Near-duplicate detection | target **>=95%** initially, improve with corpus |
| Interview/assessment email recall on curated gold set | target **~100%**; prioritize recall |
| PDF/DOCX extraction regression | **100% pass** on supported templates |
| Source outage effect | remaining sources continue without global failure |

Thresholds are not excuses to hide errors. For high-consequence classes, uncertain results are escalated.

---

## 29. Match and Ranking Philosophy

### 29.1 Separate hard eligibility from fit

Do not allow semantic similarity to override a hard restriction.

Example:

- Candidate is an excellent Data Engineer.
- Job requires legal residence in Canada.
- Candidate is not eligible.

`FitScore` may be high, but `EligibilityStatus = Ineligible`; the job is not actionable.

### 29.2 Explainability

Every recommendation should show:

- why it matched;
- must-haves met;
- likely gaps;
- uncertainty;
- location/visa condition;
- source confidence;
- recommended CV emphasis.

### 29.3 Feedback learning

User labels become evaluation and ranking data, but personal preferences do not silently rewrite objective facts.

---

## 30. Application and Action Risk Classes

### Class 0 - Read only

Discover, fetch, normalize, rank, summarize.

### Class 1 - Generate only

Generate CV/proposal/notes without external action.

### Class 2 - Prepare external action

Fill form/draft message but do not send.

### Class 3 - Controlled external action

Submit/send only for adapters and policies explicitly approved.

### Class 4 - High-value legal/commercial commitment

Tenders, contracts, binding offers, sensitive declarations. Human approval remains required.

Feature flags are granted by **adapter + action class**, not globally.

---

## 31. Security, Privacy and Compliance Workstream

### 31.1 Security baseline

- secure session management;
- MFA option for production users;
- passwordless/OAuth where appropriate;
- least privilege;
- encrypted transport;
- encrypted backups;
- secure file uploads;
- malware scanning before enterprise use;
- dependency scanning;
- Content Security Policy;
- audit logs;
- rate limiting;
- source-fetch SSRF protections;
- prompt-injection defenses for untrusted job/RFP text;
- tool allowlists for agents.

### 31.2 Prompt injection threat model

Job descriptions, CVs, procurement documents, and websites are **untrusted input**. They can contain text that attempts to instruct an LLM agent.

Rules:

- retrieved content is data, not system instruction;
- agents never receive unrestricted shell/network tools merely because a source says so;
- tool actions are policy checked outside the LLM;
- secrets are never placed in untrusted prompt context unnecessarily;
- outbound actions require deterministic permission checks.

### 31.3 Data minimization

Do not collect sensitive information merely because application sites sometimes ask for it. Voluntary demographic answers should have a user-configurable policy and should not influence match ranking.

### 31.4 Legal research baseline - not legal advice

The commercial plan must track at least:

- Egypt Labour Law No. 14 of 2025 and implementing employment/recruitment platform rules, including Ministerial Decision 272/2025.
- Egypt Personal Data Protection Law No. 151 of 2020 and applicable implementing requirements.
- Saudi employment/recruitment licensing rules before Saudi hiring/placement services.
- Saudi Personal Data Protection Law for Saudi user data.
- UAE MOHRE recruitment/mediation licensing before UAE employment intermediation.
- UAE personal-data framework.
- GDPR when EU data subjects/establishments trigger it.
- procurement platform rules per source.

Qualified counsel determines actual applicability. Agents only maintain issue lists and evidence.

---

## 32. Source/Platform Policy Registry

Maintain a machine-readable record for every source:

```yaml
source_id: example
name: Example Source
category: job_board
access:
  discovery: official_api
  detail: official_api
  submit: prohibited_or_unknown
attribution:
  required: true
rate_limits:
  documented: true
commercial_use:
  status: review_required
automation:
  read: allowed
  prepare: allowed
  submit: disabled
last_policy_reviewed: YYYY-MM-DD
policy_evidence:
  - URL
```

Policy status options:

- `verified_allowed`
- `allowed_with_conditions`
- `manual_only`
- `partnership_required`
- `unknown_disable_actions`
- `prohibited`

---

## 33. Product Metrics Dashboard

### 33.1 Founder dual-track dashboard

**Employment**
- opportunities discovered;
- eligible jobs;
- high-fit jobs;
- applications prepared/submitted;
- recruiter responses;
- interviews;
- time saved;
- qualified conversations per 100 opportunities;
- source conversion by interview.

**Independent/freelance/client**
- opportunities discovered;
- qualified/bid-worthy opportunities;
- proposals/packages prepared;
- proposals/bids submitted;
- buyer/client responses;
- discovery calls;
- won work/revenue where tracked;
- proposal effort saved;
- source conversion by qualified client conversation.

**Shared founder north-star**
- qualified human conversations per unit of founder effort;
- manual interventions per 100 recommended opportunities;
- false-positive/false-negative feedback by source and opportunity family;

### 33.2 Freelancer

- opportunities surfaced;
- bid/no-bid acceptance;
- proposals prepared/submitted;
- responses;
- calls;
- wins;
- revenue pipeline;
- user effort.

### 33.3 Employer

- vacancies;
- candidate pool searched;
- candidates meeting hard requirements;
- shortlist size;
- hiring-manager acceptance;
- interviews;
- time-to-shortlist;
- source effectiveness;
- requirement bottlenecks.

### 33.4 Business development

- opportunities/RFPs;
- qualified bids;
- proposal preparation;
- shortlist/next-stage rate;
- calls;
- wins;
- pipeline value;
- bid effort saved.

---

## 34. Product Value by Segment

### Employee

**Before:** dozens of boards, repetitive CV edits, remote eligibility confusion, forms, tracking, ghost jobs.  
**After:** a ranked legitimate feed, tailored truth-preserving application package, automated routine workflow, and attention focused on interviews.

### Freelancer

**Before:** endless project feeds, low-fit bidding, repetitive proposals, missed tenders.  
**After:** qualified demand discovery, bid/no-bid discipline, evidence-backed proposals, and attention focused on client conversations.

### Employer

**Before:** noisy applicants, inconsistent JDs, manual screening, weak market context.  
**After:** structured hiring specification, authorized talent search, explainable shortlist, market-calibration notes, and attention focused on interviewing.

### Agency / Business

**Before:** fragmented RFP/tender portals, manual qualification, repetitive proposal assembly, missed deadlines.  
**After:** opportunity radar, qualification, compliance/evidence map, proposal preparation, pipeline tracking, and attention focused on selling/delivery fit.

---

## 35. Anti-Patterns to Avoid

1. **Volume theater:** celebrating application count instead of interviews.
2. **One-source dependency:** product fails when one board changes.
3. **Generic AI CV rewriting:** hallucinated skills and shallow keyword stuffing.
4. **Universal browser bot:** brittle automation with no adapter policy.
5. **Scrape-first sourcing:** technical convenience overriding ToS/privacy.
6. **LLM decides everything:** deterministic rules replaced with probabilistic guesses.
7. **Council on every button:** agent bureaucracy slowing implementation.
8. **Microservices too early:** operational complexity before scale.
9. **Building public B2C/B2B products before founder dual-track alpha:** no early real-world learning. Founder employment and founder independent-opportunity acquisition are both core; employer/public SaaS workflows are not.
10. **Treating legal as launch-week paperwork:** employment mediation and data rules are architecture constraints.
11. **Employer black-box rankings:** unexplainable candidate rejection creates legal, ethical, and product risk.
12. **Automated spam as growth:** destroys accounts, reputation, source relationships, and product quality.

---

## 36. Backlog Priority System

Priority is based on founder usefulness first, regardless of whether the opportunity is an employment job or independent client work.

### P0 - Blocks founder dual-track usefulness

- cannot discover legitimate employment opportunities;
- cannot discover legitimate founder-usable freelance/consulting/client opportunities;
- eligibility/qualification wrong;
- CV/proposal untruthful or broken;
- canonical action path wrong;
- site inaccessible;
- data loss;
- security issue.

### P1 - Materially reduces founder friction or increases qualified conversations

- new high-quality job source;
- new high-quality founder-usable client/project/RFP source;
- better dedupe/verification;
- better job tailoring;
- better proposal/evidence tailoring;
- application/proposal assist;
- inbox/client-response classification;
- better company/buyer watchlists.

### P2 - Improves reliability/learning

- analytics;
- source health;
- company/buyer research;
- UX improvements;
- additional role/service families;
- conversion experiments.

### P3 - Family/public B2C enablers

- onboarding;
- localization;
- multi-user controls;
- support/admin;
- employment B2C productization;
- freelancer/prosumer productization.

### P4 - New organization-side segment

- employer hiring product;
- agency/business multi-user client acquisition;
- organization-level procurement response;
- marketplace/network effects.

A P4 feature may not block P0/P1 founder progress unless it is a foundational schema/security decision. Founder freelance/client acquisition is **not P4**; it is P0/P1.

## 37. Definition of Done for Any Feature

A feature is done only when:

- requirement is linked to a phase/sub-phase;
- code is reviewed by a different agent/reviewer;
- unit tests pass where relevant;
- integration/contract tests pass where relevant;
- security/privacy impact is assessed;
- source policy is recorded if external data/action is involved;
- audit/telemetry exists for consequential behavior;
- failure mode is defined;
- user-facing errors are understandable;
- documentation is updated;
- staging E2E passes;
- acceptance criteria are recorded as evidence;
- feature is behind a flag if risk warrants it;
- rollback path exists.

---

## 38. Phase Gate Report Template

This is the **default and normally only founder-facing development output for a completed phase**. Each phase ends with:

### Scope completed
- items delivered;
- items intentionally deferred.

### Test evidence
- automated tests;
- gold-set metrics;
- E2E runs;
- security checks;
- stored human/gold-set acceptance evidence where applicable;
- maker/checker repair-loop summary;
- parallel vs serial execution summary and reasons for any serial bottlenecks.

### Failures and known limitations
- open blockers;
- degraded sources;
- uncertain legal/policy issues.

### Outcome evidence
- founder/user usage;
- interviews/responses where applicable.

### Decision
- PASS
- CONDITIONAL PASS behind feature flag
- FAIL / remain in phase

### Next phase prerequisites
- exact dependencies only.

---

## 39. Recommended Repository Structure

```text
opportunityos/
├── apps/
│   ├── web/                  # Next.js
│   └── api/                  # FastAPI
├── workers/
│   ├── sources/
│   ├── matching/
│   ├── documents/
│   ├── browser/
│   ├── notifications/
│   └── agents/
├── packages/
│   ├── schemas/
│   ├── policy/
│   ├── source-sdk/
│   ├── evals/
│   └── ui/
├── sources/
│   ├── greenhouse/
│   ├── lever/
│   ├── ashby/
│   ├── himalayas/
│   ├── jobicy/
│   └── ...
├── templates/
│   ├── cv/
│   ├── proposal/
│   └── shortlist/
├── evals/
│   ├── jobs/
│   ├── eligibility/
│   ├── resumes/
│   ├── forms/
│   ├── emails/
│   ├── candidates/
│   └── tenders/
├── docs/
│   ├── MASTER_PLAN.md
│   ├── PRODUCT_CONSTITUTION.md
│   ├── SOURCE_REGISTRY.md
│   ├── AGENT_GOVERNANCE.md
│   ├── SECURITY.md
│   ├── LEGAL_ISSUES.md
│   └── adr/
├── infra/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   └── backup/
└── .github/workflows/
```

---

## 40. Source and Resource Registry

The following resources should be captured in `SOURCE_REGISTRY.md` / `SOURCE_REGISTRY.yaml` with date reviewed, terms status, and implementation notes. Links are references, not blanket permission for any specific commercial use.

### 40.1 Job discovery and ATS

**S01 - Greenhouse Job Board API**  
https://developers.greenhouse.io/job-board.html  
Use: first-party published jobs. Public GET access; employer-side submission APIs require credentials.

**S02 - Lever Postings API**  
https://github.com/lever/postings-api  
Use: first-party published Lever jobs. Treat application actions separately from public retrieval.

**S03 - Ashby Public Job Postings API**  
https://developers.ashbyhq.com/docs/public-job-posting-api  
Use: first-party Ashby-hosted career postings.

**S04 - Schema.org JobPosting**  
https://schema.org/JobPosting  
Use: structured normalization and remote/location fields on public employer pages.

**S05 - Himalayas Remote Jobs API**  
https://himalayas.app/api  
Use: global remote discovery, location restrictions, worldwide/timezone filters. Respect attribution and API limitations.

**S06 - Jobicy Remote Jobs API/RSS**  
https://jobicy.com/jobs-rss-feed  
Use: secondary remote discovery.

**S07 - We Work Remotely RSS**  
https://weworkremotely.com/remote-job-rss-feed  
Use: official RSS categories/all jobs; respect attribution.

**S08 - Remotive API**  
https://remotive.com/remote-jobs/api  
Use: secondary remote discovery; free-feed delay/terms and commercial use must be reviewed.

**S09 - Remote OK API/feed**  
https://remoteok.com/api  
Use: supplementary remote discovery under terms/attribution.

**S10 - Adzuna Developer API**  
https://developer.adzuna.com/  
Use: international job discovery subject to API key, rate limits, and commercial terms.

**S11 - WUZZUF**  
https://wuzzuf.net/  
Use: Egypt/MEA board via alerts/deep links/partnership or otherwise permitted access.

**S12 - Bayt**  
https://www.bayt.com/  
Use: MENA jobs; policy-reviewed ingestion/alerts/partnership.

**S13 - Naukrigulf**  
https://www.naukrigulf.com/  
Use: Gulf jobs; policy-reviewed ingestion/alerts/partnership.

**S14 - GulfTalent**  
https://www.gulftalent.com/  
Use: Gulf professional jobs; policy-reviewed ingestion/alerts/partnership.

**S15 - LinkedIn User Agreement / platform policy**  
https://www.linkedin.com/legal/user-agreement  
Use: policy boundary. Do not implement unauthorized scraping/bot behavior.

**S16 - Indeed Terms**  
https://www.indeed.com/legal  
Use: policy boundary. Use alerts/deep links/official routes unless permitted otherwise.

### 40.2 Front-end and engineering

**S17 - Vercel Next.js SaaS Starter**  
https://vercel.com/templates/next.js/next-js-saas-starter  
Use: forkable starting application shell; do not require Vercel hosting.

**S18 - shadcn/ui Blocks**  
https://ui.shadcn.com/blocks  
Use: editable dashboard/form/table/sidebar components.

**S19 - FastAPI**  
https://fastapi.tiangolo.com/  
Use: Python API/domain service.

**S20 - Playwright**  
https://playwright.dev/  
Use: deterministic browser automation and testing.

**S21 - Docker Compose**  
https://docs.docker.com/compose/  
Use: portable local/staging/personal deployment.

**S22 - Caddy**  
https://caddyserver.com/docs/  
Use: reverse proxy and automatic HTTPS.

**S23 - GitHub Actions**  
https://docs.github.com/actions  
Use: CI/CD initially.

**S24 - Auth.js**  
https://authjs.dev/  
Use: open-source authentication option.

**S25 - PostgreSQL**  
https://www.postgresql.org/docs/  
Use: system of record and initial worker queue.

**S26 - OWASP Top 10:2025**  
https://owasp.org/Top10/  
Use: baseline web-security risk awareness.

### 40.3 Agent/runtime resources

**S27 - OpenAI Agents SDK**  
https://openai.github.io/openai-agents-python/  
Use: candidate agent runtime for agents, handoffs, guardrails, and tracing.

**S28 - LangGraph**  
https://docs.langchain.com/oss/python/langgraph/overview  
Use: alternative/reference for durable stateful agent orchestration and human-in-the-loop workflows.

**S29 - PydanticAI**  
https://ai.pydantic.dev/  
Use: provider-flexible alternative/reference with typed agent patterns and eval/test support.

**Architecture rule:** select one primary runtime behind an internal `AgentRuntime` abstraction. Do not stack three frameworks into the core.

### 40.4 Freelancer and procurement opportunity sources

**Founder-phase rule:** every source in this subsection is evaluated during Phase 1 for founder use, in parallel with employment sources. A source may resolve to active API, public-feed, alert-ingestion, deep-link/manual, research-only, or disabled-policy status; it is not automatically postponed to Phase 8.


**S30 - Freelancer Developer API**  
https://developers.freelancer.com/  
Use: official freelance-marketplace integration candidate; sandbox available.

**S31 - Upwork automation policy**  
https://support.upwork.com/  
Use: policy boundary; automatic proposal behavior only through explicitly permitted/approved mechanisms.

**S32 - UN Global Marketplace Procurement Opportunities**  
https://www.ungm.org/Public/Notice  
Use: public UN procurement/consulting opportunities.

**S33 - UNGM Developer Center**  
https://developer.ungm.org/  
Use: official API integration reference.

**S34 - World Bank Business Opportunities**  
https://projects.worldbank.org/en/projects-operations/opportunities  
Use: current/upcoming procurement opportunities.

**S35 - World Bank Procurement Notices / Data**  
https://projects.worldbank.org/en/projects-operations/procurement  
Use: procurement notices; public data/API paths available.

**S36 - EBRD ECEPP**  
https://ecepp.ebrd.com/  
Use: EBRD-financed public-sector procurement notices.

**S37 - African Development Bank Procurement**  
https://www.afdb.org/en/news-keywords/procurement-notices  
Use: procurement notices; RSS and category feeds should be reviewed/used where available.

**S38 - EU TED Search API**  
https://docs.ted.europa.eu/api/latest/search.html  
Use: anonymous search/retrieval of published EU procurement notices for reuse/analysis.

**S39 - Saudi Etimad Tenders**  
https://tenders.etimad.sa/  
Use: official Saudi public procurement opportunity discovery; submission/account behavior separately policy-tested.

**S40 - UAE Ministry of Finance Digital Procurement Platform**  
https://mof.gov.ae/en/public-finance/government-procurement/digital-procurement-platform/  
Use: UAE federal procurement; suppliers/freelancers/foreign suppliers may have registration paths under current rules.

**S41 - Egypt General Authority for Government Services**  
https://www.gags.gov.eg/  
Use: official reference to Egyptian government procurement portal and public-contracting resources.

### 40.5 Legal/regulatory research anchors

**S42 - Egypt Ministry of Labour legislation portal**  
https://www.labour.gov.eg/  
Track Labour Law 14/2025 and implementing decisions.

**S43 - Egypt Personal Data Protection Law 151/2020**  
Track official government/legal publication and implementing decisions.

**S44 - Saudi HRSD recruitment/employment regulation**  
https://www.hrsd.gov.sa/  
Use: country compliance research before KSA recruitment/placement product.

**S45 - UAE MOHRE recruitment/mediation regulation**  
https://www.mohre.gov.ae/  
Use: country compliance research before UAE recruitment/mediation product.

### 40.6 Competitor benchmarks - not dependencies

**S46 - Uptal**  
https://uptal.com/auto-apply  
Benchmark: Gulf-focused auto-apply/tailoring positioning.

**S47 - Yalliq**  
https://yalliq.com/  
Benchmark: MENA multilingual career-copilot positioning.

**S48 - Tawzio**  
https://www.tawzio.com/  
Benchmark: Gulf/Canada career OS and workflow breadth.

Competitor monitoring should be periodic. The product moat must not depend on being the only auto-apply tool in MENA.

### 40.7 Additional founder employment/freelance discovery sources

**Founder-phase rule:** these are evaluated in Phase 1 alongside S01-S16 and S30-S41. They may be active adapters, alerts, manual/deep links, or policy-gated sources depending on their current documented access model.

**S49 - Mostaql (مستقل)**  
https://mostaql.com/freelance  
Use: major Arabic freelance-project marketplace. Founder discovery via permitted/manual/alert methods unless an official automation route is explicitly documented.

**S50 - Khamsat (خمسات)**  
https://khamsat.com/  
Use: Arabic services marketplace; useful for founder service-market/client-demand intelligence and possible account opportunities. Treat automated marketplace action as policy-gated.

**S51 - Ureed**  
https://ureed.com/  
Use: MENA-localized freelance/job marketplace; evaluate as a regional founder opportunity source through permitted access.

**S52 - Contra**  
https://contra.com/features/find-freelance-jobs  
Use: global freelance/contract opportunity discovery and independent-professional benchmark; account/action automation requires policy review.

**S53 - Guru**  
https://www.guru.com/d/jobs/  
Use: global freelance-project discovery; manual/deep-link by default unless official permitted integration is established.

**S54 - Malt**  
https://www.malt.com/c/freelancers  
Use: freelancer/client marketplace and client-invitation channel; geography/eligibility and permitted automation must be checked.

**S55 - Toptal Talent Network**  
https://www.toptal.com/freelance-jobs  
Use: high-skill freelance-network opportunity source/benchmark; discovery/onboarding behavior is account-based and should remain manual/approved unless an official integration exists.

**S56 - Arc Remote Jobs**  
https://arc.dev/en-eg/remote-jobs  
Use: Egypt-filterable remote employment and freelance/contract opportunities; evaluate alerts/deep links/partnership or other permitted ingestion.

**S57 - Working Nomads**  
https://www.workingnomads.com/remote-egypt-jobs  
Use: curated remote jobs with Egypt and contract filters; evaluate official alert/feed or permitted ingestion.

**S58 - Remote Talent Jobs**  
https://remote.com/jobs  
Use: remote/contract job discovery with explicit geography scopes including Anywhere and regional restrictions; evaluate permitted ingestion/alerts/deep links.

**S59 - Wellfound Jobs**  
https://wellfound.com/jobs  
Use: startup employment and remote-role discovery; policy-reviewed alerts/deep links/partnership rather than assumed scraping.

---

## 40A. Version 0.2 Change Record

Version 0.2 changes the founder critical path in four material ways:

1. **Freelance/consulting/client acquisition moved from a late new-segment phase into Founder Phase 1.**
2. **All legitimate sources usable by the founder as an individual are evaluated in the initial Founder Source Pack**, regardless of whether they originate from job boards, remote APIs, consulting calls, marketplaces, RFP sources, or procurement portals.
3. **Development autonomy is now explicit:** brief-in, final-phase-report-out is the default; maker/checker repair loops happen internally.
4. **Parallel execution is now a formal requirement:** the Master Agent must build a dependency DAG and maximize safe concurrency; serial execution requires an explicit technical, data, or safety dependency.

Employer hiring B2B and organization-level agency/business productization remain later because they introduce different multi-tenant, candidate-consent, fairness, legal, and commercial-commitment requirements.

---

## 41. Competitive and Strategic Moat Hypothesis

Features such as CV rewriting, job matching, browser form filling, and chat interfaces are not durable moats by themselves.

Potential defensibility comes from:

1. **Regional eligibility intelligence:** which remote/global employers really accept candidates from Egypt/MENA.
2. **Source conversion intelligence:** which sources generate real interviews or client conversations rather than dead listings.
3. **Truth-preserving professional identity graph:** reusable evidence rather than one-off generated text.
4. **Outcome dataset:** fit -> application/proposal -> response -> interview/call -> win.
5. **Multi-sided opportunity graph:** jobs, professionals, employers, projects, procurement, and businesses share a common engine.
6. **Permissioned network:** consented professionals can later be matched directly to employers/clients.
7. **Explainability and trust:** users and businesses know why the system acted.
8. **Compliance-aware source adapters:** automation is useful without being reckless.

---

## 42. Commercialization Research Questions to Answer Before Public Launch

### B2C employment

- Can the service charge job seekers directly under Egyptian recruitment/employment rules, and for exactly which software/service components?
- Is an employment agency/platform license required for the planned automated workflow?
- Which actions constitute “placement” or “mediation” versus user-controlled productivity software?
- What disclosures, language, records, support, and retention obligations apply?

### Employer/B2B

- What licensing is required to source/present candidates?
- What candidate consent/lawful basis is required?
- What contractual responsibilities arise when using employer ATS data?

### Freelancer/business development

- Which marketplace APIs permit commercial opportunity discovery and proposal submission?
- Which procurement notices permit data reuse?
- Which tender systems require registered supplier accounts and human declarations?

### Data

- Hosting/data-transfer restrictions?
- Controller/processor roles?
- retention requirements versus deletion rights?
- breach notification obligations?

These are tracked as legal issues, not guessed by the product agents.

---

## 43. First Founder Acceptance Script

The founder's first meaningful end-to-end test should be simple:

1. Sign in from a normal browser.
2. Open Opportunities.
3. Confirm new jobs have arrived from at least three independent source families.
4. Open a high-ranked role.
5. Verify source, canonical employer, location eligibility, match rationale, and gaps.
6. Click “Generate CV.”
7. Verify every factual claim against the Truth Graph.
8. Download/open the CV; confirm formatting and ATS-readable text.
9. Click “Open Application.”
10. Apply manually.
11. Mark applied.
12. Repeat over real opportunities.
13. Label bad matches immediately.
14. Observe whether ranking improves.

**If this workflow is not already easier than the founder's current job-search routine, do not move attention to flashy automation. Fix it first.**

---

## 44. First Multi-User Acceptance Script

For each family tester:

1. Receive invite.
2. Create/review Truth Graph without founder editing it for them.
3. Define role and location preferences.
4. Receive materially different opportunities from other users.
5. Generate a truthful CV.
6. Complete an application in assistive mode.
7. Verify another tester cannot access their data/artifacts.
8. Correct a mistaken extracted fact.
9. Export/delete test data in the designated workflow.
10. Rate whether the product saved meaningful time.

---

## 45. Final Build Order

The implementation order is intentionally not “all segments from day one.” It is:

1. **Architect the shared Opportunity/Truth/Workspace foundations for all segments.**
2. **Make employment discovery + tailoring useful to the founder immediately.**
3. **Expand source breadth and trust.**
4. **Remove application friction.**
5. **Close the loop with inbox and outcomes.**
6. **Prove multi-user isolation and usability with private testers.**
7. **Clear legal/commercial gates for public employment B2C.**
8. **Reuse the engine for freelancer opportunity acquisition.**
9. **Reuse job-market intelligence plus authorized candidate data for employer B2B.**
10. **Reuse procurement/RFP intelligence for agency/business client acquisition.**
11. **Unify only after each wedge has evidence of value.**

This sequence protects the founder's immediate goal while preserving the larger company thesis.

---

## 46. Final Product Principle

OpportunityOS should not try to replace human relationships. It should remove everything around them that wastes attention.

The platform's job is to:

- watch more places than a human can;
- remember more context than a human should have to;
- filter harder and earlier;
- verify source legitimacy;
- understand constraints;
- select the right evidence;
- prepare the right documents;
- complete repetitive work;
- track every outcome;
- learn what converts;
- and interrupt the user only when the next step benefits from a human being human.

**Businesses need qualified people. Professionals need meaningful work. Freelancers and agencies need clients. The platform's common purpose is to reduce the search, filtering, paperwork, and repetition between those parties so they can spend their attention deciding whether they actually belong together.**

---

# Appendix A - Initial Founder Alpha Source Priority

The founder alpha is dual-track. Source implementation is organized as **parallel squads sharing one adapter contract**. “Evaluate in Phase 1” does not mean every site receives a bot; it means each source gets a deliberate access status and is included through the strongest legitimate method available.

## A1. Employment squad - Phase 1 priority

**Core machine-readable / first-party:**

1. Greenhouse
2. Lever
3. Ashby
4. Direct company watchlist / canonical employer pages
5. Himalayas
6. Jobicy
7. We Work Remotely
8. Remotive
9. Remote OK
10. Adzuna where key/terms permit
11. Schema.org JobPosting first-party parser

**Coverage through permitted alerts/deep links/research:**

12. WUZZUF
13. Bayt
14. Naukrigulf
15. GulfTalent
16. LinkedIn job alerts/deep links
17. Indeed alerts/deep links
18. Remote Talent
19. Working Nomads
20. Arc
21. Wellfound

## A2. Independent/freelance/consulting/client squad - Phase 1 priority

**Official/public/API-oriented sources:**

1. Freelancer.com developer API/sandbox candidate
2. UNGM public opportunities/developer API
3. World Bank business/procurement opportunities
4. AfDB procurement/consultant notices
5. EBRD ECEPP
6. EU TED Search API
7. Saudi Etimad public opportunity discovery
8. UAE federal Digital Procurement Platform discovery
9. Egypt government procurement resources
10. direct buyer/vendor/RFP/consultant-call pages

**Marketplace/network sources evaluated for permitted/manual/alert use:**

11. Mostaql
12. Ureed
13. Contra
14. Guru
15. Malt
16. Toptal
17. Arc freelance/contract roles
18. Khamsat service-demand/seller channel
19. user-configured buyer/RFP watchlists
20. marketplace/email alerts where direct automation is not permitted

**Founder Alpha rule:** none of these sources is deferred merely because it is “freelance.” The Master Agent may ship a source as `manual_deeplink` or `alert_ingestion` while a more automated adapter remains unavailable or prohibited.

---

# Appendix B - Initial Founder Alpha Feature Flags

```text
# Shared founder experience
EMPLOYMENT_MODE=on
FOUNDER_CLIENT_OPPORTUNITY_MODE=on
FOUNDATION_CAPABILITY_GRAPH=on

# Employment source adapters
SOURCE_GREENHOUSE=on_after_adapter_gate
SOURCE_LEVER=on_after_adapter_gate
SOURCE_ASHBY=on_after_adapter_gate
SOURCE_HIMALAYAS=on_after_adapter_gate
SOURCE_JOBICY=on_after_adapter_gate
SOURCE_WWR=shadow_until_adapter_gate
SOURCE_REMOTIVE=shadow_until_adapter_gate
SOURCE_REMOTEOK=shadow_until_adapter_gate
SOURCE_REMOTE_TALENT=manual_or_alert_until_adapter_gate
SOURCE_ARC=manual_or_alert_until_adapter_gate
SOURCE_WELLFOUND=manual_or_alert_until_adapter_gate

# Independent opportunity sources
SOURCE_FREELANCER_API=shadow_until_adapter_gate
SOURCE_UNGM=on_after_adapter_gate
SOURCE_WORLDBANK=on_after_adapter_gate
SOURCE_AFDB=on_after_adapter_gate
SOURCE_EBRD=on_after_adapter_gate
SOURCE_TED=on_after_adapter_gate
SOURCE_ETIMAD=manual_or_public_read_until_policy_gate
SOURCE_UAE_PROCUREMENT=manual_or_public_read_until_policy_gate
SOURCE_MOSTAQL=manual_or_alert_until_policy_gate
SOURCE_UREED=manual_or_alert_until_policy_gate
SOURCE_CONTRA=manual_or_alert_until_policy_gate
SOURCE_GURU=manual_until_policy_gate

# Decisions and artifacts
AUTO_REJECT_INELIGIBLE=shadow
AUTO_NO_BID_UNQUALIFIED=shadow
AUTO_GENERATE_CV=on
AUTO_GENERATE_PROPOSAL=on
AUTO_GENERATE_EVIDENCE_PACK=on

# External action
AUTO_FILL_APPLICATION=off_until_phase4
AUTO_SUBMIT_APPLICATION=off
AUTO_PREPARE_PROPOSAL_ACTION=off_until_phase4
AUTO_SUBMIT_PROPOSAL=off
AUTO_SEND_OUTREACH=off
EMAIL_AUTO_TRACK=off_until_phase5

# Productization modes
FAMILY_INVITES=off_until_phase6
PUBLIC_EMPLOYMENT_B2C=off_until_phase7
PUBLIC_FREELANCER_B2C=off_until_phase8
EMPLOYER_MODE=off_until_phase9
ORGANIZATION_AGENCY_MODE=off_until_phase10
```

---

# Appendix C - Agent Decision Packet Schema

```yaml
decision_id: ADR-XXXX
problem: ""
phase: ""
urgency: ""
constraints:
  product_constitution: []
  legal_policy: []
  technical: []
  cost: []
current_state: ""
options:
  - id: A
    description: ""
  - id: B
    description: ""
evidence: []
unknowns: []
reversibility: low|medium|high
external_side_effect: true|false
human_gate_required: true|false
required_tests: []
```

---

# Appendix D - Minimum Source Adapter Test Checklist

- [ ] official/permitted access path documented;
- [ ] terms/attribution requirement recorded;
- [ ] test fixture saved;
- [ ] schema parser test;
- [ ] pagination test;
- [ ] duplicate rerun test;
- [ ] timeout test;
- [ ] 429/rate-limit test;
- [ ] malformed record test;
- [ ] canonical URL test;
- [ ] location parsing test;
- [ ] disabled-adapter test;
- [ ] provenance persisted;
- [ ] last-verified timestamp persisted;
- [ ] health metric emitted;
- [ ] commercial-use status recorded;
- [ ] action permissions recorded separately from read permissions.

---

# Appendix E - Minimum Generated Artifact Test Checklist

- [ ] correct user/workspace;
- [ ] correct target opportunity;
- [ ] correct contact details;
- [ ] dates unchanged unless approved formatting only;
- [ ] titles unchanged unless approved alias;
- [ ] completed/in-progress credential labels correct;
- [ ] no planned credential presented as held;
- [ ] every achievement supported;
- [ ] no invented tools;
- [ ] no invented years of experience;
- [ ] no hidden keyword stuffing;
- [ ] ATS text extraction passes;
- [ ] rendered output has no clipping;
- [ ] generated-claim -> evidence links complete;
- [ ] version and template ID stored.

---

# Appendix F - Minimum Employer Shortlist Test Checklist

- [ ] vacancy requirements approved by employer;
- [ ] must-have versus nice-to-have separated;
- [ ] inferred requirements visibly marked;
- [ ] candidate source authorized;
- [ ] candidate consent/lawful basis recorded where required;
- [ ] protected attributes excluded from ranking features;
- [ ] evidence shown for each match;
- [ ] gaps/uncertainty shown;
- [ ] no fabricated candidate facts;
- [ ] human hiring decision retained;
- [ ] audit event recorded;
- [ ] retention/delete policy applied.

---

# Appendix G - Minimum Tender/Proposal Test Checklist

- [ ] issuer/source canonical;
- [ ] deadline verified;
- [ ] eligibility verified;
- [ ] mandatory registrations identified;
- [ ] required documents extracted;
- [ ] bid/no-bid rationale;
- [ ] proposal statements evidence-backed;
- [ ] no invented clients/case studies;
- [ ] terms and submission channel checked;
- [ ] binding/legal declarations require human approval;
- [ ] final submission receipt stored when permitted;
- [ ] versioned artifact retained.

---

# Appendix H - Research Notes on Verified Resource Capabilities

These notes capture current implementation-relevant facts and should be revalidated before commercial launch because APIs and terms change.

- Greenhouse documents public Job Board API GET endpoints for published jobs; application submission endpoints are a different permission domain and may require employer-side credentials.
- Lever exposes published job postings through its Postings API; application write capabilities are not assumed to be publicly available to candidate-side software.
- Ashby exposes a public job-posting endpoint for hosted job boards with structured posting fields and application URLs.
- Himalayas currently exposes a public remote-jobs API with filters including location restrictions/worldwide/timezone and requires appropriate attribution.
- Remotive offers public API/RSS discovery but its free API may be delayed and has usage/attribution conditions.
- We Work Remotely publishes official RSS feeds.
- Jobicy publishes API/RSS access for remote jobs.
- Freelancer.com publishes a developer API and sandbox, making it materially different from marketplaces where unauthorized automation is prohibited.
- UNGM has public procurement opportunities and a developer center/API ecosystem; actual bid submission method varies by issuing organization.
- World Bank publishes current/upcoming/potential procurement opportunities and public procurement notice data.
- EU TED's Search API permits anonymous retrieval of published procurement notices for reuse/analysis.
- UAE Ministry of Finance's Digital Procurement Platform connects federal entities with suppliers and currently supports supplier categories including foreign suppliers and freelancers, subject to registration requirements.
- Saudi Etimad exposes public tender search pages; participation/submission rules must be separately respected.
- AfDB publishes procurement notices and RSS feeds for several opportunity categories.
- OWASP Top 10:2025 is used as a baseline security awareness reference, not as the complete security program.
- Mostaql is an Arabic freelance-project marketplace where freelancers browse open projects and submit offers; use should default to permitted/manual/alert modes unless an official automation route is documented.
- Khamsat is an Arabic digital-services marketplace and is more naturally treated as a seller/service-demand channel than as a conventional project feed.
- Ureed positions itself as a MENA-localized freelance platform where professionals can browse jobs and submit proposals.
- Contra publishes global/remote freelance opportunities and contractor discovery workflows; account/action automation still requires separate policy review.
- Guru publishes a searchable freelance-jobs marketplace where freelancers send quotes to projects.
- Malt connects freelancers with project proposals from clients and should be treated as an account/geography-dependent opportunity channel.
- Toptal operates a screened talent network with remote freelance opportunities; access depends on joining/qualifying for its network.
- Arc exposes Egypt-filterable remote employment and freelance/contract opportunities, making it useful for founder coverage even when ingestion remains manual/alert/deep-link.
- Working Nomads publishes Egypt-filterable remote jobs including contract roles.
- Remote Talent publishes remote jobs with explicit Anywhere, regional, and timezone scope labels that can improve location-eligibility interpretation.
- Wellfound provides startup job discovery, including remote jobs; automated access should remain policy-reviewed rather than assumed.

---

# Appendix I - Autonomous Phase Brief Template

This is the preferred input handed to the Master Development Agent. The founder should not need to decompose engineering tasks manually.

```yaml
phase_id: ""
objective: ""
why_now: ""
user_value:
  founder_employment: ""
  founder_independent_work: ""
non_negotiables: []
explicitly_out_of_scope: []
allowed_sources_and_tools: []
preapproved_external_actions: []
forbidden_external_actions: []
legal_policy_constraints: []
security_privacy_constraints: []
budget_cap: ""
concurrency_cap: ""
required_acceptance_metrics: {}
required_gold_sets: []
required_deliverables: []
required_documentation: []
final_report_only: true
```

Master Agent obligations after receiving this brief:

- derive the technical/product task graph independently;
- identify parallel-safe and serial/gated work;
- instantiate the needed council roles;
- spawn specialist maker and checker agents;
- keep ordinary implementation decisions internal;
- execute autonomous repair loops after failed tests/reviews;
- stop consequential branches safely when a hard gate is encountered;
- continue all other independent work;
- return the final Phase Gate Report with evidence, not a stream of routine questions.

---

# Appendix J - Founder Setup Completion Packet

Before fully autonomous development begins, the founder should be able to mark this packet complete or explicitly unknown. Unknown is acceptable when the system is instructed not to guess.

## J1 Career/employment identity

- [ ] master CV/history imported;
- [ ] employers, titles, dates verified;
- [ ] achievements/evidence classified;
- [ ] skills/tools verified;
- [ ] certifications status recorded;
- [ ] role families and exclusions defined;
- [ ] geography/remote/timezone/work-authorization rules defined;
- [ ] salary/notice/travel/relocation policies defined.

## J2 Independent-professional identity

- [ ] services/capabilities defined;
- [ ] portfolio/case studies/evidence imported;
- [ ] client/project types defined;
- [ ] rates/budget policy defined or marked unknown;
- [ ] capacity/availability defined;
- [ ] engagement/geography constraints defined;
- [ ] legal-entity/vendor limitations marked;
- [ ] proposal claims and forbidden claims defined.

## J3 Action policy

- [ ] Green answers approved;
- [ ] Yellow policies approved;
- [ ] Red Questions/Commitments listed;
- [ ] daily application/proposal caps defined;
- [ ] external-action default set;
- [ ] no-spam policy accepted.

## J4 Infrastructure and autonomy

- [ ] repository/domain/server under founder control;
- [ ] secrets/password manager/SSH ready;
- [ ] LLM/provider budget and credentials ready where used;
- [ ] source credentials ready where required;
- [ ] backup destination ready;
- [ ] Product Constitution approved;
- [ ] agent permissions/concurrency/budget caps approved;
- [ ] final-report-only default approved;
- [ ] phase brief template approved.

## J5 Evaluation seed

- [ ] employment good/bad examples seeded or Shadow Mode allowed to collect them;
- [ ] independent opportunity good/bad examples seeded or Shadow Mode allowed to collect them;
- [ ] CV truth traps seeded;
- [ ] proposal truth/commercial traps seeded;
- [ ] email/response examples seeded when available.

**Completion rule:** if J1-J4 are complete enough to prevent guessing and the minimum Phase 0 technical environment exists, the Master Agent should be able to execute later phases autonomously within the pre-approved boundaries.

