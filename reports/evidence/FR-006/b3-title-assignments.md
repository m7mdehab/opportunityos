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

**Mapped to `other`: 37/67 (55.2%).** This is expected and does not contradict the brief's >= 95%
acceptance bar: that bar is measured over work order A1's fixture corpus once it lands (a later,
separate run the Master will order -- see this order's "Facts established by the Master" section),
not over this hand-assembled, deliberately generic-heavy list. Roughly half of these titles were
picked specifically *because* they are generic single-word or procurement/RFP-style test fixtures
("Engineer", "Consultant", "Advisory RFP", "Staff Engineer") that legitimately have no identifiable
role family from the title text alone -- that is what a real, honest `other` bucket looks like, not
a defect in the family rules. The titles below are listed in full, not summarized.

## Titles mapped to `other` (37)

- Modernization of Enterprise Data Analytics & Cloud Services
- Consultancy on National Climate Adaptation Data Platform
- Digital Transformation & Data Architecture Consultancy
- Advisory RFP
- Multi-Year Enterprise Transformation
- Consulting Assignment
- Massive Infrastructure Transformation
- General Advisory RFP
- Cloud Security Assessment
- Procurement Tender
- Contract Engineer
- Data Advisory RFP
- Cloud Infrastructure Advisory RFP
- Sales Role
- Marketing Coordinator
- Engineer
- Senior Python Engineer
- Software Engineer - Payments
- Staff Engineer
- Software Engineer
- Remote Developer
- Senior Architect
- Software Architect
- Junior Architect
- Data Services
- Senior Engineer
- Data Services RFP
- Data Pipeline SOW
- Consultant
- Field Operations Lead — Emergency Response
- Independent Grant Writing Contract
- Data Governance Advisor (Procurement Notice)
- Regional Partnerships Contractor
- Program Evaluation Lead
- Compliance Monitoring Consultant
- Digital Inclusion Strategy Consultant
- Staff AI

## Full assignment table

| Title | Source file | Family | Level | Matched rule |
|---|---|---|---|---|
| Senior Systems Engineer - Distributed Caching | `opportunity/fixtures/greenhouse_cloudflare.json` | `devops_platform` | `senior` | `devops_platform#alias:6:systems engineer` |
| Data Analyst - Product Insights | `opportunity/fixtures/greenhouse_cloudflare.json` | `analytics_bi` | `unspecified` | `analytics_bi#alias:0:data analyst` |
| Principal Backend Architect | `opportunity/fixtures/himalayas.json` | `backend` | `principal` | `backend#alias:3:backend architect` |
| Lead DevOps Engineer | `opportunity/fixtures/remotive.json` | `devops_platform` | `senior` | `devops_platform#alias:0:devops engineer` |
| Senior Machine Learning Engineer | `opportunity/fixtures/lever_shyftlabs.json` | `ml_ai_engineering` | `senior` | `ml_ai_engineering#alias:0:machine learning engineer` |
| Junior Frontend Developer | `opportunity/fixtures/lever_shyftlabs.json` | `web_frontend` | `junior` | `web_frontend#alias:2:frontend developer` |
| Senior Fullstack Engineer | `opportunity/fixtures/remote_ok.json` | `web_frontend` | `senior` | `web_frontend#alias:9:fullstack engineer` |
| Modernization of Enterprise Data Analytics & Cloud Services | `opportunity/fixtures/eu_ted.json` | `other` | `unspecified` | `other#no_match` |
| Consultancy on National Climate Adaptation Data Platform | `opportunity/fixtures/ungm.json` | `other` | `unspecified` | `other#no_match` |
| Digital Transformation & Data Architecture Consultancy | `opportunity/fixtures/world_bank.json` | `other` | `unspecified` | `other#no_match` |
| Datadog: Senior Backend Systems Engineer | `opportunity/fixtures/we_work_remotely.xml` | `devops_platform` | `senior` | `devops_platform#alias:6:systems engineer` |
| Advisory RFP | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Enterprise Cloud Migration Tender | `matching/test_adversarial.py` | `data_migration` | `unspecified` | `data_migration#alias:1:cloud migration` |
| Statistical Consulting Services | `matching/test_adversarial.py` | `data_science` | `unspecified` | `data_science#pattern:1` |
| Multi-Year Enterprise Transformation | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Consulting Assignment | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Massive Infrastructure Transformation | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| General Advisory RFP | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Cloud Security Assessment | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Procurement Tender | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Contract Engineer | `matching/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Data Engineer | `matching/test_artifacts_e2e.py` | `data_engineering` | `unspecified` | `data_engineering#alias:0:data engineer` |
| Platform Engineer | `matching/test_artifacts_e2e.py` | `devops_platform` | `unspecified` | `devops_platform#alias:2:platform engineer` |
| Data Advisory RFP | `matching/test_artifacts_e2e.py` | `other` | `unspecified` | `other#no_match` |
| Cloud Infrastructure Advisory RFP | `matching/test_compiler.py` | `other` | `unspecified` | `other#no_match` |
| Senior Distributed Systems Architect | `matching/test_gold_set.py` | `devops_platform` | `senior` | `devops_platform#alias:7:systems architect` |
| Junior Frontend React Developer | `matching/test_gold_set.py` | `web_frontend` | `junior` | `web_frontend#alias:5:react developer` |
| Sales Role | `api/test_api.py` | `other` | `unspecified` | `other#no_match` |
| Backend Engineer | `api/test_api.py` | `backend` | `unspecified` | `backend#alias:0:backend engineer` |
| Marketing Coordinator | `api/test_api.py` | `other` | `unspecified` | `other#no_match` |
| Senior Backend Engineer | `api/test_api.py` | `backend` | `senior` | `backend#alias:0:backend engineer` |
| Senior Software Engineer, Backend | `api/test_api.py` | `backend` | `senior` | `backend#pattern:1` |
| Backend Engineer Intern | `api/test_api.py` | `backend` | `intern` | `backend#alias:0:backend engineer` |
| Staff Backend Engineer | `opportunity/test_persistence.py` | `backend` | `staff` | `backend#alias:0:backend engineer` |
| Engineer | `opportunity/test_models.py` | `other` | `unspecified` | `other#no_match` |
| Senior Python Engineer | `opportunity/test_dedupe.py` | `other` | `senior` | `other#no_match` |
| Systems Engineer - Cloudflare Workers | `opportunity/test_dedupe.py` | `devops_platform` | `unspecified` | `devops_platform#alias:6:systems engineer` |
| Software Engineer - Payments | `opportunity/test_dedupe.py` | `other` | `unspecified` | `other#no_match` |
| Staff Engineer | `inbox/test_pipeline_and_notifications.py` | `other` | `staff` | `other#no_match` |
| Senior Data Engineer | `recon/test_audit.py` | `data_engineering` | `senior` | `data_engineering#alias:0:data engineer` |
| Full Stack Developer | `recon/test_audit.py` | `web_frontend` | `unspecified` | `web_frontend#alias:7:full stack developer` |
| Software Engineer | `recon/test_unmapped.py` | `other` | `unspecified` | `other#no_match` |
| Remote Developer | `recon/test_unmapped.py` | `other` | `unspecified` | `other#no_match` |
| DevOps Engineer | `recon/test_unmapped.py` | `devops_platform` | `unspecified` | `devops_platform#alias:0:devops engineer` |
| Frontend Engineer | `recon/test_unmapped.py` | `web_frontend` | `unspecified` | `web_frontend#alias:0:frontend engineer` |
| Senior Architect | `inbox/test_correlation.py` | `other` | `senior` | `other#no_match` |
| Lead Data Architect | `inbox/test_correlation.py` | `data_engineering` | `senior` | `data_engineering#alias:6:data architect` |
| Software Architect | `inbox/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Junior Architect | `inbox/test_adversarial.py` | `other` | `junior` | `other#no_match` |
| Data Services | `inbox/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Senior Engineer | `security/test_prompt_injection.py` | `other` | `senior` | `other#no_match` |
| Data Services RFP | `outbound/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Data Pipeline SOW | `outbound/test_adversarial.py` | `other` | `unspecified` | `other#no_match` |
| Consultant | `outbound/test_adapters.py` | `other` | `unspecified` | `other#no_match` |
| Senior Localization Program Manager | `web/tests/e2e/seed_real.py` | `project_program_management` | `senior` | `project_program_management#alias:1:program manager` |
| Field Operations Lead — Emergency Response | `web/tests/e2e/seed_real.py` | `other` | `senior` | `other#no_match` |
| Independent Grant Writing Contract | `web/tests/e2e/seed_real.py` | `other` | `unspecified` | `other#no_match` |
| Data Governance Advisor (Procurement Notice) | `web/tests/e2e/seed_real.py` | `other` | `unspecified` | `other#no_match` |
| Regional Partnerships Contractor | `web/tests/e2e/seed_real.py` | `other` | `unspecified` | `other#no_match` |
| Program Evaluation Lead | `web/tests/e2e/seed_real.py` | `other` | `senior` | `other#no_match` |
| Compliance Monitoring Consultant | `web/tests/e2e/seed_real.py` | `other` | `unspecified` | `other#no_match` |
| Youth Skills Program Coordinator | `web/tests/e2e/seed_real.py` | `project_program_management` | `unspecified` | `project_program_management#alias:4:program coordinator` |
| Digital Inclusion Strategy Consultant | `web/tests/e2e/seed_real.py` | `other` | `unspecified` | `other#no_match` |
| Senior Systems Architect | `storage/test_postgres_integration.py` | `devops_platform` | `senior` | `devops_platform#alias:7:systems architect` |
| Staff AI | `storage/test_postgres_integration.py` | `other` | `staff` | `other#no_match` |
| Staff Platform Engineer | `storage/test_postgres_integration.py` | `devops_platform` | `staff` | `devops_platform#alias:2:platform engineer` |
| Remote Data Engineer | `truth/test_predicates.py` | `data_engineering` | `unspecified` | `data_engineering#alias:0:data engineer` |

## Known scope conflict found while implementing this order (reported, not silently worked around)

Changing `api/filters.py`'s `target_roles` `default_mode` to `rank_only` (required by this order)
causes `api.test_api.FilterSeedSyncTest.test_migration_seed_matches_filter_definitions_defaults`
to fail. That test guards a *pre-existing* invariant: `storage/migrations/versions/
0003_provenance_identity.py` carries `_D3_FILTER_SEED`, a deliberate independent literal copy of
every filter's default (per that migration's own module docstring), and the test asserts it never
drifts from `api.filters.FILTER_DEFINITIONS`. Fixing the drift requires editing that migration
file, which is explicitly frozen for this work order (`storage/**`, "any migration"), and this
order separately says not to write a new migration either. This is exactly the scenario this
order's own text anticipated ("if that is impossible without a migration, stop and report it as a
scope question rather than writing `0005`") -- reported here rather than worked around by touching
a frozen file or deleting/weakening the guard test. `api/test_api.py`'s own new
`TargetRolesDefaultModeTest.test_target_roles_default_mode_is_rank_only` (added by this order,
in-scope) passes and directly asserts the required default; the drift is confined to the one
pre-existing seed-sync test named above. See B3.3's raw run for the exact failure.
