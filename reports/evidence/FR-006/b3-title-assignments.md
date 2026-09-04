# B3 title-assignment table (BRIEF-FR-006)

Every title below is a real, already-committed string taken from a file already in this
repository -- `opportunity/fixtures/*` payloads (posting titles actually returned by the source
adapters' fixtures) and realistic posting-title literals used as fixtures across the test suites
(`matching/`, `api/`, `opportunity/`, `inbox/`, `recon/`, `security/`, `outbound/`,
`web/tests/e2e/seed_real.py`, `storage/`, `truth/`). None are invented for this table. `docs/
SOURCE_EVIDENCE.md` (BRIEF-001 recon run) was checked and contains only aggregate counts and an
ATS company watchlist, no individual posting titles, so it contributes no rows here.

67 titles are listed (>= the 60 required). Each row was produced by actually calling
`matching.title_family.normalize_title(title)` -- see B3.4's raw run output in the phase
evidence/report for this work order -- not hand-assigned. Family/level/rule columns are exactly
what the function returned.

**Resolution:** all 67/67 titles resolved (no exception, no `None`; `other` is itself a resolved,
valid outcome per `normalize_title`'s contract).

## Council review #1 defect repair (this section revised)

Two defects from council review #1 changed this evidence:

1. **`other` was absorbing real engineering titles.** A new `software_engineering` family (a
   deliberately generic fallback, evaluated last, after every specific family) now catches a
   bare Engineer / Developer / Architect / Programmer title with no more specific domain signal.
   `matching/title_families.yaml` and `matching/title_family.py` were changed; see this work
   order's return for the diff summary. Eleven titles that previously landed in `other` now
   resolve to `software_engineering`: `Senior Python Engineer`, `Software Engineer - Payments`,
   `Software Engineer`, `Staff Engineer`, `Senior Engineer`, `Engineer`, `Contract Engineer`,
   `Remote Developer`, `Senior Architect`, `Software Architect`, `Junior Architect`. Level
   extraction was re-verified to keep working through this change (`Senior Architect` -> senior,
   `Junior Architect` -> junior; see `matching/test_title_family.py::
   TestSoftwareEngineeringFallbackFamily`).

2. **The `other` count conflated two different populations.** The brief's >= 95% acceptance bar
   is ">= 95% of fixture-corpus **titles** map to a family" -- procurement/RFP/tender/SOW notice
   titles are not posting titles, and mixing them with genuine role titles the taxonomy simply
   failed to place made the single combined percentage unmeasurable as a taxonomy-quality signal.
   The remaining 26 `other` rows are now split into two labelled groups below, and both a
   combined rate and a role-only rate are reported. No title was removed from the table to
   improve either percentage -- all 67 rows, including every `other` row, remain in the full
   table.

## `other` rows, split into two groups (26 total)

### Group (a) -- not a role posting (procurement notice / RFP / tender / SOW / consultancy scope) -- 17

- Modernization of Enterprise Data Analytics & Cloud Services (TED procurement notice title)
- Consultancy on National Climate Adaptation Data Platform (UNGM RFP notice title)
- Digital Transformation & Data Architecture Consultancy (World Bank procurement notice title)
- Advisory RFP
- Multi-Year Enterprise Transformation
- Consulting Assignment
- Massive Infrastructure Transformation
- General Advisory RFP
- Cloud Security Assessment
- Procurement Tender
- Data Advisory RFP
- Cloud Infrastructure Advisory RFP
- Data Services (procurement-track fixture; buyer "Gov Contracting", source "ted")
- Data Services RFP
- Data Pipeline SOW
- Independent Grant Writing Contract
- Data Governance Advisor (Procurement Notice)

### Group (b) -- a role title the taxonomy failed to place -- 9

- Sales Role
- Marketing Coordinator
- Consultant
- Field Operations Lead — Emergency Response
- Regional Partnerships Contractor
- Program Evaluation Lead
- Compliance Monitoring Consultant
- Digital Inclusion Strategy Consultant
- Staff AI

## Mapping-rate arithmetic (both numbers, per council review #1)

- **Combined `other` rate over all 67 titles:** 26/67 = **38.8%** (17 group-(a) non-role titles +
  9 group-(b) unplaced role titles).
- **Role-posting-only rate** (excludes the 17 group-(a) non-role titles from the denominator,
  since they are not posting titles and the brief's acceptance bar is defined over posting
  titles): 67 - 17 = 50 role-posting titles; 50 - 9 (group b) = 41 successfully mapped to a real
  family. **41/50 = 82.0%** of genuine role-posting titles in this hand-assembled list map to a
  family (equivalently, group (b)'s 9/50 = 18.0% is the unplaced-role rate). This 82.0% is a
  measurement over this order's own assembled list, not the brief's >= 95% corpus-wide bar --
  that bar is measured over work order A1's fixture corpus once it lands, per this order's
  "Facts established by the Master" section.

## Full assignment table (all 67 rows)

| Title | Source file | Family | Level | Matched rule |
|---|---|---|---|---|
| Senior Systems Engineer - Distributed Caching | `opportunity/fixtures/greenhouse_cloudflare.json` | `devops_platform` | `senior` | `devops_platform#alias:6:systems engineer` |
| Data Analyst - Product Insights | `opportunity/fixtures/greenhouse_cloudflare.json` | `analytics_bi` | `unspecified` | `analytics_bi#alias:0:data analyst` |
| Principal Backend Architect | `opportunity/fixtures/himalayas.json` | `backend` | `principal` | `backend#alias:3:backend architect` |
| Lead DevOps Engineer | `opportunity/fixtures/remotive.json` | `devops_platform` | `senior` | `devops_platform#alias:0:devops engineer` |
| Senior Machine Learning Engineer | `opportunity/fixtures/lever_shyftlabs.json` | `ml_ai_engineering` | `senior` | `ml_ai_engineering#alias:0:machine learning engineer` |
| Junior Frontend Developer | `opportunity/fixtures/lever_shyftlabs.json` | `web_frontend` | `junior` | `web_frontend#alias:2:frontend developer` |
| Senior Fullstack Engineer | `opportunity/fixtures/remote_ok.json` | `web_frontend` | `senior` | `web_frontend#alias:9:fullstack engineer` |
| Modernization of Enterprise Data Analytics & Cloud Services | `opportunity/fixtures/eu_ted.json` | `other` (a) | `unspecified` | `other#no_match` |
| Consultancy on National Climate Adaptation Data Platform | `opportunity/fixtures/ungm.json` | `other` (a) | `unspecified` | `other#no_match` |
| Digital Transformation & Data Architecture Consultancy | `opportunity/fixtures/world_bank.json` | `other` (a) | `unspecified` | `other#no_match` |
| Datadog: Senior Backend Systems Engineer | `opportunity/fixtures/we_work_remotely.xml` | `devops_platform` | `senior` | `devops_platform#alias:6:systems engineer` |
| Advisory RFP | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Enterprise Cloud Migration Tender | `matching/test_adversarial.py` | `data_migration` | `unspecified` | `data_migration#alias:1:cloud migration` |
| Statistical Consulting Services | `matching/test_adversarial.py` | `data_science` | `unspecified` | `data_science#pattern:1` |
| Multi-Year Enterprise Transformation | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Consulting Assignment | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Massive Infrastructure Transformation | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| General Advisory RFP | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Cloud Security Assessment | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Procurement Tender | `matching/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Contract Engineer | `matching/test_adversarial.py` | `software_engineering` | `unspecified` | `software_engineering#alias:2:engineer` |
| Data Engineer | `matching/test_artifacts_e2e.py` | `data_engineering` | `unspecified` | `data_engineering#alias:0:data engineer` |
| Platform Engineer | `matching/test_artifacts_e2e.py` | `devops_platform` | `unspecified` | `devops_platform#alias:2:platform engineer` |
| Data Advisory RFP | `matching/test_artifacts_e2e.py` | `other` (a) | `unspecified` | `other#no_match` |
| Cloud Infrastructure Advisory RFP | `matching/test_compiler.py` | `other` (a) | `unspecified` | `other#no_match` |
| Senior Distributed Systems Architect | `matching/test_gold_set.py` | `devops_platform` | `senior` | `devops_platform#alias:7:systems architect` |
| Junior Frontend React Developer | `matching/test_gold_set.py` | `web_frontend` | `junior` | `web_frontend#alias:5:react developer` |
| Sales Role | `api/test_api.py` | `other` (b) | `unspecified` | `other#no_match` |
| Backend Engineer | `api/test_api.py` | `backend` | `unspecified` | `backend#alias:0:backend engineer` |
| Marketing Coordinator | `api/test_api.py` | `other` (b) | `unspecified` | `other#no_match` |
| Senior Backend Engineer | `api/test_api.py` | `backend` | `senior` | `backend#alias:0:backend engineer` |
| Senior Software Engineer, Backend | `api/test_api.py` | `backend` | `senior` | `backend#pattern:1` |
| Backend Engineer Intern | `api/test_api.py` | `backend` | `intern` | `backend#alias:0:backend engineer` |
| Staff Backend Engineer | `opportunity/test_persistence.py` | `backend` | `staff` | `backend#alias:0:backend engineer` |
| Engineer | `opportunity/test_models.py` | `software_engineering` | `unspecified` | `software_engineering#alias:2:engineer` |
| Senior Python Engineer | `opportunity/test_dedupe.py` | `software_engineering` | `senior` | `software_engineering#alias:2:engineer` |
| Systems Engineer - Cloudflare Workers | `opportunity/test_dedupe.py` | `devops_platform` | `unspecified` | `devops_platform#alias:6:systems engineer` |
| Software Engineer - Payments | `opportunity/test_dedupe.py` | `software_engineering` | `unspecified` | `software_engineering#alias:0:software engineer` |
| Staff Engineer | `inbox/test_pipeline_and_notifications.py` | `software_engineering` | `staff` | `software_engineering#alias:2:engineer` |
| Senior Data Engineer | `recon/test_audit.py` | `data_engineering` | `senior` | `data_engineering#alias:0:data engineer` |
| Full Stack Developer | `recon/test_audit.py` | `web_frontend` | `unspecified` | `web_frontend#alias:7:full stack developer` |
| Software Engineer | `recon/test_unmapped.py` | `software_engineering` | `unspecified` | `software_engineering#alias:0:software engineer` |
| Remote Developer | `recon/test_unmapped.py` | `software_engineering` | `unspecified` | `software_engineering#alias:3:developer` |
| DevOps Engineer | `recon/test_unmapped.py` | `devops_platform` | `unspecified` | `devops_platform#alias:0:devops engineer` |
| Frontend Engineer | `recon/test_unmapped.py` | `web_frontend` | `unspecified` | `web_frontend#alias:0:frontend engineer` |
| Senior Architect | `inbox/test_correlation.py` | `software_engineering` | `senior` | `software_engineering#alias:4:architect` |
| Lead Data Architect | `inbox/test_correlation.py` | `data_engineering` | `senior` | `data_engineering#alias:6:data architect` |
| Software Architect | `inbox/test_adversarial.py` | `software_engineering` | `unspecified` | `software_engineering#alias:4:architect` |
| Junior Architect | `inbox/test_adversarial.py` | `software_engineering` | `junior` | `software_engineering#alias:4:architect` |
| Data Services | `inbox/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Senior Engineer | `security/test_prompt_injection.py` | `software_engineering` | `senior` | `software_engineering#alias:2:engineer` |
| Data Services RFP | `outbound/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Data Pipeline SOW | `outbound/test_adversarial.py` | `other` (a) | `unspecified` | `other#no_match` |
| Consultant | `outbound/test_adapters.py` | `other` (b) | `unspecified` | `other#no_match` |
| Senior Localization Program Manager | `web/tests/e2e/seed_real.py` | `project_program_management` | `senior` | `project_program_management#alias:1:program manager` |
| Field Operations Lead — Emergency Response | `web/tests/e2e/seed_real.py` | `other` (b) | `senior` | `other#no_match` |
| Independent Grant Writing Contract | `web/tests/e2e/seed_real.py` | `other` (a) | `unspecified` | `other#no_match` |
| Data Governance Advisor (Procurement Notice) | `web/tests/e2e/seed_real.py` | `other` (a) | `unspecified` | `other#no_match` |
| Regional Partnerships Contractor | `web/tests/e2e/seed_real.py` | `other` (b) | `unspecified` | `other#no_match` |
| Program Evaluation Lead | `web/tests/e2e/seed_real.py` | `other` (b) | `senior` | `other#no_match` |
| Compliance Monitoring Consultant | `web/tests/e2e/seed_real.py` | `other` (b) | `unspecified` | `other#no_match` |
| Youth Skills Program Coordinator | `web/tests/e2e/seed_real.py` | `project_program_management` | `unspecified` | `project_program_management#alias:4:program coordinator` |
| Digital Inclusion Strategy Consultant | `web/tests/e2e/seed_real.py` | `other` (b) | `unspecified` | `other#no_match` |
| Senior Systems Architect | `storage/test_postgres_integration.py` | `devops_platform` | `senior` | `devops_platform#alias:7:systems architect` |
| Staff AI | `storage/test_postgres_integration.py` | `other` (b) | `staff` | `other#no_match` |
| Staff Platform Engineer | `storage/test_postgres_integration.py` | `devops_platform` | `staff` | `devops_platform#alias:2:platform engineer` |
| Remote Data Engineer | `truth/test_predicates.py` | `data_engineering` | `unspecified` | `data_engineering#alias:0:data engineer` |

`(a)` / `(b)` annotations on `other` rows refer to the two groups defined above.

## Filter-seed guard resolution (defect 4, council review #1)

The original report noted `api.test_api.FilterSeedSyncTest.test_migration_seed_matches_
filter_definitions_defaults` failed because migration 0003's independent literal filter-seed copy
(`_D3_FILTER_SEED`) went stale the moment `target_roles`'s default changed, and fixing that file is
frozen for this work order. Per the Master's resolution (BRIEF-FR-006 work order A1M owns
migration `0004`, which carries the `target_roles -> rank_only` data migration), the test itself
was rewritten to assert the invariant it actually means: the seeded state **at Alembic head**
(0003's seed composed with every later revision's declared overrides), not 0003 read in isolation.
`storage/migrations/versions/0003_provenance_identity.py` was not edited. With no revision after
0003 present in this worktree yet, the rewritten test skips cleanly and names the missing revision
(`0004`) rather than asserting a value it cannot verify at head; see this work order's return for
the raw B3.3 run showing `OK (skipped=1)`.
