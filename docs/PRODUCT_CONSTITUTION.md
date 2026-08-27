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
