# Predicate contract table (BRIEF-FR-005 section 10)

Generated from `truth/predicates.py`. **72 predicates** registered: **62 PROJECTED**, **10 ASSERTION_ONLY**.

A predicate is PROJECTED when `truth/graph.py` emits it from a profile field, and
ASSERTION_ONLY when it can only arrive via the truth pack's top-level `assertions:`
section. `matching/` imports every name from this registry and spells none itself; a
contract test globs every non-test file in `matching/` to keep that true.

Before this brief there was no registry, and `matching/` read eighteen predicate
spellings the graph never emits. The most consequential was `responsibility.item`,
which made `responsibility_scope` a flat 0.50 for every founder since BRIEF-004.

## ASSERTION_ONLY - supplied by the pack, not projected from a profile

These are the ones that silently return nothing when the founder's pack omits them,
which is why three filters needed an `unavailable_reason`.

| predicate | owning pack section |
|---|---|
| `capacity.team_size` | assertions |
| `career.goal` | assertions |
| `career.target_role` | assertions |
| `location.city` | assertions |
| `location.country` | assertions |
| `preference.fulltime_onsite_premium_monthly` | assertions |
| `preference.track` | assertions |
| `residence.city` | assertions |
| `residence.country` | assertions |
| `residence.jurisdiction` | assertions |

## PROJECTED - emitted by truth/graph.py from a profile field (62)

| predicate | profile field |
|---|---|
| `achievement.statement` | Achievement.statement |
| `capability.delivery_language` | CapabilityProfile.delivery_languages |
| `capability.excluded_industry` | CapabilityProfile.excluded_industries |
| `capability.target_industry` | CapabilityProfile.target_industries |
| `capability_profile.capacity` | CapabilityProfile.capacity |
| `capability_profile.never_claims` | CapabilityProfile.never_claims |
| `capability_profile.portfolio` | CapabilityProfile.portfolio |
| `capability_profile.red_lines` | CapabilityProfile.red_lines |
| `capability_profile.services` | CapabilityProfile.services |
| `capability_profile.tools` | CapabilityProfile.tools |
| `capacity.annual_turnover_usd` | BusinessCapacity.annual_turnover_usd |
| `capacity.available_from` | BusinessCapacity.available_from |
| `capacity.bid_bond_capacity_usd` | BusinessCapacity.bid_bond_capacity_usd |
| `capacity.currency` | BusinessCapacity.currencies |
| `capacity.hours_per_week` | BusinessCapacity.hours_per_week |
| `capacity.legal_capacity` | BusinessCapacity.legal_capacity |
| `capacity.max_project_value` | BusinessCapacity.max_project_value |
| `capacity.min_project_value` | BusinessCapacity.min_project_value |
| `capacity.onsite_willingness` | BusinessCapacity.onsite_willingness |
| `capacity.service_region` | BusinessCapacity.service_regions |
| `career_profile.certifications` | CareerProfile.certifications |
| `career_profile.education` | CareerProfile.education |
| `career_profile.employment` | CareerProfile.employment |
| `career_profile.languages` | CareerProfile.languages |
| `career_profile.never_claims` | CareerProfile.never_claims |
| `career_profile.red_lines` | CareerProfile.red_lines |
| `career_profile.skills` | CareerProfile.skills |
| `career_profile.work_authorizations` | CareerProfile.work_authorizations |
| `certification.credential_id` | CertificationRecord.credential_id |
| `certification.credential_url` | CertificationRecord.credential_url |
| `certification.expiry_date` | CertificationRecord.expiry_date |
| `certification.issued_date` | CertificationRecord.issued_date |
| `certification.issuer` | CertificationRecord.issuer |
| `certification.name` | CertificationRecord.name |
| `certification.state` | CertificationRecord.state |
| `education.end_date` | EducationRecord.end_date |
| `education.institution` | EducationRecord.institution |
| `education.qualification` | EducationRecord.qualification |
| `education.start_date` | EducationRecord.start_date |
| `employment.achievement` | EmploymentRecord.achievements |
| `employment.end_date` | EmploymentRecord.end_date |
| `employment.market_facing_title` | EmploymentRecord.market_facing_title |
| `employment.organization` | EmploymentRecord.organization |
| `employment.responsibility` | EmploymentRecord.responsibilities |
| `employment.start_date` | EmploymentRecord.start_date |
| `employment.title` | EmploymentRecord.title |
| `language.language` | LanguageRecord.language |
| `language.proficiency` | LanguageRecord.proficiency |
| `portfolio.outcome` | PortfolioItem.outcome |
| `portfolio.summary` | PortfolioItem.summary |
| `portfolio.title` | PortfolioItem.title |
| `portfolio.url` | PortfolioItem.url |
| `profile.approved_summary` | CareerProfile.approved_summaries |
| `service.deliverable` | ServiceRecord.deliverables |
| `service.description` | ServiceRecord.description |
| `service.engagement_type` | ServiceRecord.engagement_types |
| `service.name` | ServiceRecord.name |
| `skill.name` | SkillRecord.name |
| `skill.proficiency` | SkillRecord.proficiency |
| `work_authorization.expiry_date` | WorkAuthorization.expiry_date |
| `work_authorization.jurisdiction` | WorkAuthorization.jurisdiction |
| `work_authorization.status` | WorkAuthorization.status |
