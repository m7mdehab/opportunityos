"""Synthetic, non-PII fixtures and gold claims for the truth engine."""

from __future__ import annotations

from datetime import date

from .graph import TruthGraph
from .models import (
    Achievement,
    ApprovedPhrase,
    AssertionType,
    AtomicAssertion,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    CertificationRecord,
    CertificationState,
    EducationRecord,
    EmploymentRecord,
    EngagementType,
    EvidenceRecord,
    Identity,
    LanguageRecord,
    MetricAssertion,
    MetricVerification,
    NeverClaimRule,
    PortfolioItem,
    ProhibitedConceptCategory,
    RedLineRule,
    ServiceRecord,
    SkillRecord,
    VerificationStatus,
    WorkAuthorization,
)


VERIFIED_CLAIMS = (
    "Built a synthetic reporting pipeline that reduced processing time by 40%.",
    "Uses Python for data engineering.",
    "Offers analytics pipeline assessments.",
    "Planning to pursue the Example Cloud Architect certification.",
)

UNBACKED_CLAIMS = (
    "Managed a team of 50 engineers.",
    "Generated $2 million in client revenue.",
    "Is fluent in Japanese.",
)

PROHIBITED_CLAIMS = (
    "Serves Fortune 500 clients.",
    "Guarantees a 300% return on every engagement.",
    "Completed the Example Cloud Architect certification.",
)


def synthetic_evidence() -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord("ev-org", "Synthetic Analytics Ltd", "synthetic_cv", "employment.0.organization", metadata={"organization": "Synthetic Analytics Ltd"}),
        EvidenceRecord("ev-title", "Data Engineer with responsibilities including Maintained synthetic data pipelines.", "synthetic_cv", "employment.0.title", metadata={"title": "Data Engineer"}),
        EvidenceRecord("ev-dates", "2022-01-01 to 2024-06-30", "synthetic_cv", "employment.0.dates"),
        EvidenceRecord(
            "ev-achievement",
            "Built a synthetic reporting pipeline at Synthetic Analytics Ltd that reduced processing time by 40%.",
            "synthetic_cv", "employment.0.achievements.0",
            metadata={"subject_id": "achievement-verified"},
        ),
        EvidenceRecord(
            "ev-python", "Uses Python for data engineering.", "synthetic_cv", "skills.0",
            assertion_type=AssertionType.NORMALIZED_FACT,
        ),
        EvidenceRecord("ev-degree", "BSc in Example Systems from Example Institute from 2017-09-01 to 2021-06-30.", "synthetic_cv", "education.0"),
        EvidenceRecord("ev-language", "English professional proficiency", "synthetic_cv", "languages.0"),
        EvidenceRecord("ev-work-auth", "Authorized to work in Exampleland", "synthetic_cv", "work_authorizations.0", metadata={"jurisdiction": "Exampleland", "status": "authorized"}),
        EvidenceRecord(
            "ev-cert-plan", "Planning to pursue the Example Cloud Architect certification from Example Cloud Foundation.",
            "synthetic_profile", "certifications.0",
            metadata={"name": "Example Cloud Architect", "issuer": "Example Cloud Foundation"},
        ),
        EvidenceRecord(
            "ev-service", "Analytics pipeline assessment. Offers analytics pipeline assessments with Fixed price and Consultant tender engagement models delivering Evidence-backed findings and Prioritized remediation plan.",
            "synthetic_capability_pack", "services.0",
            assertion_type=AssertionType.DERIVED_CAPABILITY,
        ),
        EvidenceRecord(
            "ev-portfolio", "Delivered a synthetic data quality assessment for an example dataset.",
            "synthetic_capability_pack", "portfolio.0",
        ),
        EvidenceRecord(
            "ev-capacity", "Available for 20 hours per week from 2026-09-01 with min project value 1000 and max 10000 USD across MENA and WORLDWIDE on a case_by_case onsite basis.",
            "synthetic_capability_pack", "capacity",
        ),
        EvidenceRecord(
            "ev-legal-null", None, "synthetic_capability_pack", "capacity.legal_capacity",
            verification_status=VerificationStatus.EXPLICIT_NULL,
        ),
        EvidenceRecord(
            "ev-approx", "Approximately 25 source systems were assessed.",
            "synthetic_cv", "employment.0.achievements.1",
            verification_status=VerificationStatus.APPROXIMATE,
        ),
        EvidenceRecord(
            "ev-profile", "Synthetic data engineer focused on reliable analytics systems.",
            "synthetic_cv", "profile",
        ),
        EvidenceRecord(
            "ev-cap-profile", "Target industries Technology and Development, excluded Weapons, delivering in English language.",
            "synthetic_capability_pack", "capability",
        ),
        EvidenceRecord(
            "ev-identity",
            "Jordan A. Synthetic is a Synthetic Data Engineering Leader based in Synthetic City, "
            "Exampleland. Email jordan.synthetic@example.com, phone +1-555-0100, LinkedIn "
            "https://linkedin.com/in/jordan-synthetic, GitHub https://github.com/jordan-synthetic, "
            "website https://jordan-synthetic.example.",
            "synthetic_identity", "identity",
        ),
        EvidenceRecord(
            "ev-phrase-motivation-1",
            "I am motivated by building reliable, evidence-backed data systems that teams can trust.",
            "synthetic_identity", "approved_phrases.0",
        ),
        EvidenceRecord(
            "ev-phrase-motivation-2",
            "I thrive on turning ambiguous data problems into dependable, well-tested pipelines.",
            "synthetic_identity", "approved_phrases.1",
        ),
        EvidenceRecord(
            "ev-phrase-closing-1",
            "I would welcome the opportunity to bring this focus on reliability to your team.",
            "synthetic_identity", "approved_phrases.2",
        ),
        EvidenceRecord(
            "ev-phrase-closing-2",
            "Thank you for considering my application; I look forward to discussing how I can contribute.",
            "synthetic_identity", "approved_phrases.3",
        ),
    )


def synthetic_identity() -> Identity:
    return Identity(
        id="identity",
        name="Jordan A. Synthetic",
        evidence_ids=("ev-identity",),
        headline="Synthetic Data Engineering Leader",
        email="jordan.synthetic@example.com",
        phone="+1-555-0100",
        linkedin="https://linkedin.com/in/jordan-synthetic",
        github="https://github.com/jordan-synthetic",
        website="https://jordan-synthetic.example",
        location_city="Synthetic City",
        location_country="Exampleland",
    )


def synthetic_approved_phrases() -> tuple[ApprovedPhrase, ...]:
    return (
        ApprovedPhrase(
            "phrase-motivation-1",
            "I am motivated by building reliable, evidence-backed data systems that teams can trust.",
            ("ev-phrase-motivation-1",), ("motivation",),
        ),
        ApprovedPhrase(
            "phrase-motivation-2",
            "I thrive on turning ambiguous data problems into dependable, well-tested pipelines.",
            ("ev-phrase-motivation-2",), ("motivation",),
        ),
        ApprovedPhrase(
            "phrase-closing-1",
            "I would welcome the opportunity to bring this focus on reliability to your team.",
            ("ev-phrase-closing-1",), ("closing",),
        ),
        ApprovedPhrase(
            "phrase-closing-2",
            "Thank you for considering my application; I look forward to discussing how I can contribute.",
            ("ev-phrase-closing-2",), ("closing",),
        ),
    )


def synthetic_career_profile() -> CareerProfile:
    return CareerProfile(
        id="career-synthetic",
        evidence_ids=("ev-profile",),
        employment=(
            EmploymentRecord(
                id="job-synthetic", organization="Synthetic Analytics Ltd", title="Data Engineer",
                start_date=date(2022, 1, 1), end_date=date(2024, 6, 30),
                evidence_ids=("ev-org", "ev-title", "ev-dates"),
                achievements=(
                    Achievement(
                        "achievement-verified",
                        "Built a synthetic reporting pipeline that reduced processing time by 40%.",
                        ("ev-achievement",), MetricVerification.VERIFIED,
                    ),
                    Achievement(
                        "achievement-approximate",
                        "Approximately 25 source systems were assessed.",
                        ("ev-approx",), MetricVerification.APPROXIMATE,
                    ),
                ),
                responsibilities=("Maintained synthetic data pipelines.",),
            ),
        ),
        education=(
            EducationRecord(
                "education-synthetic", "Example Institute", "BSc in Example Systems",
                date(2017, 9, 1), date(2021, 6, 30), ("ev-degree",),
            ),
        ),
        certifications=(
            CertificationRecord(
                "cert-planned", "Example Cloud Architect", "Example Cloud Foundation",
                CertificationState.PLANNED, ("ev-cert-plan",),
            ),
        ),
        skills=(SkillRecord("skill-python", "Python", ("ev-python",)),),
        languages=(LanguageRecord("language-english", "English", "professional", ("ev-language",)),),
        work_authorizations=(
            WorkAuthorization("auth-exampleland", "Exampleland", "authorized", ("ev-work-auth",)),
        ),
        approved_summaries=("Synthetic data engineer focused on reliable analytics systems.",),
        red_lines=(
            RedLineRule(
                "red-guarantee",
                r"\b(?:guarantee\w*|100%\s*(?:success|satisfaction|result|roi)|unconditional\w*\s*(?:promise\w*|assur\w*)|zero\s*risk|assure\w*\s*(?:positive\s*)?(?:outcome|roi|results?)|promis\w*\s*(?:positive\s*)?(?:success|results?|outcome))\b",
                "outcomes cannot be guaranteed",
            ),
        ),
        never_claims=(
            NeverClaimRule(
                "never-guarantee",
                ProhibitedConceptCategory.GUARANTEED_OUTCOME,
                "outcomes cannot be guaranteed",
                r"\b(?:guarantee\w*|100%\s*(?:success|satisfaction|result|roi)|unconditional\w*\s*(?:promise\w*|assur\w*)|zero\s*risk|assure\w*\s*(?:positive\s*)?(?:outcome|roi|results?)|promis\w*\s*(?:positive\s*)?(?:success|results?|outcome))\b",
                ("guarantee", "100% success"),
            ),
            NeverClaimRule(
                "never-f500",
                ProhibitedConceptCategory.FORTUNE_500_PRESTIGE,
                "no client evidence exists",
                r"\b(?:fortune\s*500|global\s*2000|f500|top\s*fortune)\b",
                ("Fortune 500 clients", "Fortune 500"),
            ),
        ),
    )


def synthetic_capability_profile() -> CapabilityProfile:
    return CapabilityProfile(
        id="capability-synthetic",
        evidence_ids=("ev-cap-profile",),
        services=(
            ServiceRecord(
                "service-assessment", "Analytics pipeline assessment",
                "Offers analytics pipeline assessments with Fixed price and Consultant tender engagement models delivering Evidence-backed findings and Prioritized remediation plan.", ("ev-service",),
                (EngagementType.FIXED_PRICE, EngagementType.CONSULTANT_TENDER),
                ("Evidence-backed findings", "Prioritized remediation plan"),
            ),
        ),
        portfolio=(
            PortfolioItem(
                "portfolio-assessment", "Synthetic data quality assessment",
                "Delivered a synthetic data quality assessment for an example dataset.",
                ("ev-portfolio",),
            ),
        ),
        capacity=BusinessCapacity(
            "capacity-synthetic", ("ev-capacity", "ev-legal-null"),
            available_from=date(2026, 9, 1), hours_per_week=20,
            min_project_value=1000, max_project_value=10000, currencies=("USD",),
            service_regions=("MENA", "WORLDWIDE"), onsite_willingness="case_by_case",
            legal_capacity=None,
        ),
        target_industries=("Technology", "Development"),
        excluded_industries=("Weapons",),
        delivery_languages=("English",),
        tools=(SkillRecord("tool-python", "Python", ("ev-python",)),),
        never_claims=(
            NeverClaimRule(
                "never-turnkey",
                ProhibitedConceptCategory.UNAUTHORIZED_LEGAL_PRACTICE,
                "not a legal service",
                r"\b(?:turnkey\s*legal\s*advice|licensed\s*legal\s*counsel|formal\s*legal\s*(?:advice|counsel|representation)|binding\s*counsel|licensed\s*attorney)\b",
                ("turnkey legal advice",),
            ),
        ),
    )


def synthetic_graph() -> TruthGraph:
    metric_40 = MetricAssertion(
        id="metric-synthetic-pipeline",
        subject_id="achievement-verified",
        numeric_value=40,
        unit="%",
        context="reduced processing time by 40%",
        verification_status=MetricVerification.VERIFIED,
        evidence_ids=("ev-achievement",),
    )
    graph = TruthGraph(synthetic_evidence(), metrics=(metric_40,))
    graph.add_career_profile(synthetic_career_profile())
    graph.add_capability_profile(synthetic_capability_profile())
    graph.add_identity(synthetic_identity())
    for phrase in synthetic_approved_phrases():
        graph.add_approved_phrase(phrase)
    return graph


# ---------------------------------------------------------------------------
# Founder-shaped synthetic pack (BRIEF-FR-005 D1 e2e fixture)
# ---------------------------------------------------------------------------
# Every name below is obviously fake ("Nile Systems", "Delta Freight", "Atlas
# Freight Holdings", ...). None of this is the founder's real employment
# history -- it exists only to give the compiler and validator a pack SHAPED
# like a real founder pack (nine employment roles including internships and
# three concurrent roles inside one corporate group, five certifications, 38
# skills, and preference assertions) instead of the much smaller shipped
# `synthetic_graph()` template. This is committed to the repository, so it
# must never carry real personal data (see AGENTS.md / BRIEF-FR-005 D1).

_FOUNDER_ROLES = (
    {
        "rid": "intern-nile",
        "org": "Nile Systems",
        "title": "Data Analyst Intern",
        "start": date(2016, 6, 1),
        "end": date(2016, 8, 31),
        "responsibility": "Cleaned and validated shipment tracking datasets for the analytics team.",
    },
    {
        "rid": "intern-delta",
        "org": "Delta Freight",
        "title": "Software Engineering Intern",
        "start": date(2017, 6, 1),
        "end": date(2017, 8, 31),
        "responsibility": "Built internal reporting scripts for the logistics operations desk.",
    },
    {
        "rid": "junior-sahara",
        "org": "Sahara Cloud Ltd",
        "title": "Junior Backend Developer",
        "start": date(2017, 9, 1),
        "end": date(2018, 12, 31),
        "responsibility": "Maintained REST API endpoints for the billing platform.",
    },
    {
        "rid": "mid-sahara",
        "org": "Sahara Cloud Ltd",
        "title": "Backend Developer",
        "start": date(2019, 1, 1),
        "end": date(2020, 3, 31),
        "responsibility": "Owned the billing platform's data ingestion service.",
    },
    {
        "rid": "freelance-cedar",
        "org": "Cedar Analytics Group",
        "title": "Freelance Data Consultant",
        "start": date(2019, 1, 1),
        "end": date(2019, 6, 30),
        "responsibility": "Delivered a data quality assessment for a regional retail client.",
    },
    {
        "rid": "data-atlas",
        "org": "Atlas Freight Holdings",
        "title": "Data Engineer",
        "start": date(2020, 4, 1),
        "end": date(2022, 12, 31),
        "responsibility": "Built and operated ETL pipelines for group-wide shipment data.",
        "achievement": "Reduced nightly ETL runtime by 30% across the group's shipment data pipeline.",
        "metric": (30, "%"),
    },
    # Three concurrent roles inside one corporate group (2023-01-01 to
    # 2026-08-31): a parent-company platform lead role plus a matching data
    # engineer role at each of two subsidiaries, held at the same time.
    {
        "rid": "group-holdings",
        "org": "Atlas Freight Holdings",
        "title": "Group Data Platform Lead",
        "start": date(2023, 1, 1),
        "end": date(2026, 8, 31),
        "responsibility": "Led the shared data platform serving all group subsidiaries.",
        "achievement": "Reduced group-wide pipeline latency by 35% for the shared data platform.",
        "metric": (35, "%"),
    },
    {
        "rid": "group-logistics",
        "org": "Atlas Freight Logistics",
        "title": "Data Engineer",
        "start": date(2023, 1, 1),
        "end": date(2026, 8, 31),
        "responsibility": "Maintained logistics-specific data marts on the shared group platform.",
    },
    {
        "rid": "group-analytics",
        "org": "Atlas Freight Analytics",
        "title": "Data Engineer",
        "start": date(2023, 1, 1),
        "end": date(2026, 8, 31),
        "responsibility": "Maintained analytics-specific data marts on the shared group platform.",
    },
)

_FOUNDER_CERTIFICATIONS = (
    {
        "cid": "cert-data-eng",
        "name": "Certified Data Engineering Associate",
        "issuer": "Nile Institute",
        "state": CertificationState.COMPLETED,
        "issued": date(2019, 5, 1),
    },
    {
        "cid": "cert-cloud-practitioner",
        "name": "Cloud Platform Practitioner",
        "issuer": "Delta Cloud Academy",
        "state": CertificationState.COMPLETED,
        "issued": date(2020, 11, 1),
    },
    {
        "cid": "cert-applied-stats",
        "name": "Applied Statistics Certificate",
        "issuer": "Sahara Institute of Technology",
        "state": CertificationState.COMPLETED,
        "issued": date(2021, 7, 1),
    },
    {
        "cid": "cert-data-governance",
        "name": "Advanced Data Governance Certificate",
        "issuer": "Atlas Learning Group",
        "state": CertificationState.COMPLETED,
        "issued": date(2023, 2, 1),
    },
    {
        "cid": "cert-group-architect",
        "name": "Certified Group Analytics Architect",
        "issuer": "Cedar Certification Board",
        "state": CertificationState.PLANNED,
        "issued": None,
    },
)

_FOUNDER_SKILLS = (
    "Python", "SQL", "Data Modeling", "ETL Pipelines", "Apache Kafka", "Apache Airflow",
    "dbt", "Docker", "Kubernetes", "AWS", "Google Cloud Platform", "Microsoft Azure",
    "Terraform", "CI CD Automation", "Git", "Linux Administration", "Bash Scripting",
    "Java", "Scala", "Apache Spark", "Hadoop", "NoSQL Databases", "MongoDB",
    "PostgreSQL", "Redis", "GraphQL", "REST API Design", "Microservices Architecture",
    "Agile Delivery", "Scrum Facilitation", "Stakeholder Communication", "Data Visualization",
    "Tableau", "Power BI", "Statistics", "Machine Learning", "A/B Testing", "Data Governance",
)
assert len(_FOUNDER_SKILLS) == 38, "founder-shaped pack must carry exactly 38 skills"


def _skill_slug(name: str) -> str:
    return name.casefold().replace(" ", "-").replace("/", "-")


def founder_shaped_evidence() -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []

    for role in _FOUNDER_ROLES:
        rid = role["rid"]
        records.append(EvidenceRecord(
            f"ev-{rid}-org", role["org"], "founder_shaped_cv", f"employment.{rid}.organization",
            metadata={"organization": role["org"]},
        ))
        records.append(EvidenceRecord(
            f"ev-{rid}-title", f"{role['title']} at {role['org']}.",
            "founder_shaped_cv", f"employment.{rid}.title",
            metadata={"title": role["title"]},
        ))
        records.append(EvidenceRecord(
            f"ev-{rid}-dates", f"{role['start'].isoformat()} to {role['end'].isoformat()}",
            "founder_shaped_cv", f"employment.{rid}.dates",
        ))
        records.append(EvidenceRecord(
            f"ev-{rid}-resp", role["responsibility"],
            "founder_shaped_cv", f"employment.{rid}.responsibilities.0",
        ))
        if "achievement" in role:
            records.append(EvidenceRecord(
                f"ev-{rid}-achievement", f"{role['achievement']} Delivered at {role['org']}.",
                "founder_shaped_cv", f"employment.{rid}.achievements.0",
                metadata={"subject_id": f"achievement-{rid}"},
            ))

    for cert in _FOUNDER_CERTIFICATIONS:
        cid = cert["cid"]
        if cert["state"] is CertificationState.PLANNED:
            content = f"Planning to pursue the {cert['name']} certification from {cert['issuer']}."
        else:
            content = f"Completed the {cert['name']} certification from {cert['issuer']} in {cert['issued'].isoformat()}."
        records.append(EvidenceRecord(
            f"ev-{cid}", content, "founder_shaped_profile", f"certifications.{cid}",
            metadata={"name": cert["name"], "issuer": cert["issuer"]},
        ))

    for skill in _FOUNDER_SKILLS:
        slug = _skill_slug(skill)
        records.append(EvidenceRecord(
            f"ev-skill-{slug}", skill, "founder_shaped_cv", f"skills.{slug}",
        ))

    records.append(EvidenceRecord(
        "ev-founder-education", "BSc in Computer Science from Nile Institute from 2013-09-01 to 2017-06-30.",
        "founder_shaped_cv", "education.0",
    ))
    records.append(EvidenceRecord(
        "ev-founder-language-en", "English professional proficiency", "founder_shaped_cv", "languages.0",
    ))
    records.append(EvidenceRecord(
        "ev-founder-language-ar", "Arabic native proficiency", "founder_shaped_cv", "languages.1",
    ))
    records.append(EvidenceRecord(
        "ev-founder-work-auth", "Authorized to work in Egypt", "founder_shaped_cv", "work_authorizations.0",
        metadata={"jurisdiction": "Egypt", "status": "authorized"},
    ))
    records.append(EvidenceRecord(
        "ev-founder-profile", "Data engineer with group-scale platform experience across freight and logistics data.",
        "founder_shaped_cv", "profile",
    ))

    # Capability profile (procurement / freelance track)
    records.append(EvidenceRecord(
        "ev-founder-cap-profile",
        "Target industries Logistics and Technology, excluded Weapons, delivering in English language.",
        "founder_shaped_capability_pack", "capability",
    ))
    records.append(EvidenceRecord(
        "ev-founder-service-platform",
        "Group data platform advisory. Offers group data platform advisory with Fixed price and Consultant tender "
        "engagement models delivering Evidence-backed findings and Prioritized remediation plan.",
        "founder_shaped_capability_pack", "services.0",
        assertion_type=AssertionType.DERIVED_CAPABILITY,
    ))
    records.append(EvidenceRecord(
        "ev-founder-service-etl",
        "ETL pipeline assessment. Offers ETL pipeline assessment with Time and materials and Retainer "
        "engagement models delivering Evidence-backed findings and Prioritized remediation plan.",
        "founder_shaped_capability_pack", "services.1",
        assertion_type=AssertionType.DERIVED_CAPABILITY,
    ))
    records.append(EvidenceRecord(
        "ev-founder-portfolio-group",
        "Delivered a shared data platform migration for a multi-subsidiary freight group.",
        "founder_shaped_capability_pack", "portfolio.0",
    ))
    records.append(EvidenceRecord(
        "ev-founder-portfolio-etl",
        "Delivered an ETL pipeline reliability review for a regional logistics operator.",
        "founder_shaped_capability_pack", "portfolio.1",
    ))
    records.append(EvidenceRecord(
        "ev-founder-capacity",
        "Available for 25 hours per week from 2026-10-02 with min project value 2000 and max 20000 USD "
        "across MENA and WORLDWIDE on a case_by_case onsite basis.",
        "founder_shaped_capability_pack", "capacity",
    ))

    # Preference assertions (evidence backing only -- the AtomicAssertions
    # themselves are added directly to the graph in founder_shaped_graph()).
    records.append(EvidenceRecord(
        "ev-founder-pref-target-role", "Target role: Data Engineer.", "founder_shaped_profile", "preferences.target_role",
    ))
    records.append(EvidenceRecord(
        "ev-founder-pref-track", "Preferred track: employment.", "founder_shaped_profile", "preferences.track",
    ))
    records.append(EvidenceRecord(
        "ev-founder-pref-goal",
        "Career goal: lead a shared data platform for a distributed engineering group.",
        "founder_shaped_profile", "preferences.goal",
    ))
    records.append(EvidenceRecord(
        "ev-founder-pref-residence", "Resident of Egypt.", "founder_shaped_profile", "preferences.residence",
    ))
    records.append(EvidenceRecord(
        "ev-founder-pref-premium",
        "Full-time on-site premium threshold: 50000 EGP per month.",
        "founder_shaped_profile", "preferences.fulltime_onsite_premium_monthly",
    ))

    records.append(EvidenceRecord(
        "ev-founder-identity",
        "Riley K. Founder is a Group Data Platform Lead based in Cairo, Egypt. Email "
        "riley.founder@example.com, phone +20-555-0101, LinkedIn "
        "https://linkedin.com/in/riley-founder-shaped, GitHub https://github.com/riley-founder-shaped, "
        "website https://riley-founder-shaped.example.",
        "founder_shaped_identity", "identity",
    ))
    records.append(EvidenceRecord(
        "ev-founder-phrase-motivation-1",
        "I am driven to build data platforms that a distributed engineering group can rely on.",
        "founder_shaped_identity", "approved_phrases.0",
    ))
    records.append(EvidenceRecord(
        "ev-founder-phrase-motivation-2",
        "I care about turning fragmented shipment data into one dependable, shared platform.",
        "founder_shaped_identity", "approved_phrases.1",
    ))
    records.append(EvidenceRecord(
        "ev-founder-phrase-closing-1",
        "I would welcome the chance to bring this platform-lead experience to your team.",
        "founder_shaped_identity", "approved_phrases.2",
    ))
    records.append(EvidenceRecord(
        "ev-founder-phrase-closing-2",
        "Thank you for your time; I look forward to discussing how I can contribute to your group.",
        "founder_shaped_identity", "approved_phrases.3",
    ))

    return tuple(records)


def founder_shaped_identity() -> Identity:
    return Identity(
        id="identity",
        name="Riley K. Founder",
        evidence_ids=("ev-founder-identity",),
        headline="Group Data Platform Lead",
        email="riley.founder@example.com",
        phone="+20-555-0101",
        linkedin="https://linkedin.com/in/riley-founder-shaped",
        github="https://github.com/riley-founder-shaped",
        website="https://riley-founder-shaped.example",
        location_city="Cairo",
        location_country="Egypt",
    )


def founder_shaped_approved_phrases() -> tuple[ApprovedPhrase, ...]:
    return (
        ApprovedPhrase(
            "phrase-founder-motivation-1",
            "I am driven to build data platforms that a distributed engineering group can rely on.",
            ("ev-founder-phrase-motivation-1",), ("motivation",),
        ),
        ApprovedPhrase(
            "phrase-founder-motivation-2",
            "I care about turning fragmented shipment data into one dependable, shared platform.",
            ("ev-founder-phrase-motivation-2",), ("motivation",),
        ),
        ApprovedPhrase(
            "phrase-founder-closing-1",
            "I would welcome the chance to bring this platform-lead experience to your team.",
            ("ev-founder-phrase-closing-1",), ("closing",),
        ),
        ApprovedPhrase(
            "phrase-founder-closing-2",
            "Thank you for your time; I look forward to discussing how I can contribute to your group.",
            ("ev-founder-phrase-closing-2",), ("closing",),
        ),
    )


def founder_shaped_career_profile() -> CareerProfile:
    employment = tuple(
        EmploymentRecord(
            id=role["rid"],
            organization=role["org"],
            title=role["title"],
            start_date=role["start"],
            end_date=role["end"],
            evidence_ids=(
                f"ev-{role['rid']}-org", f"ev-{role['rid']}-title",
                f"ev-{role['rid']}-dates", f"ev-{role['rid']}-resp",
            ),
            achievements=(
                (Achievement(
                    f"achievement-{role['rid']}",
                    role["achievement"],
                    (f"ev-{role['rid']}-achievement",),
                    MetricVerification.VERIFIED,
                ),)
                if "achievement" in role else ()
            ),
            responsibilities=(role["responsibility"],),
        )
        for role in _FOUNDER_ROLES
    )

    certifications = tuple(
        CertificationRecord(
            cert["cid"], cert["name"], cert["issuer"], cert["state"],
            (f"ev-{cert['cid']}",), issued_date=cert["issued"],
        )
        for cert in _FOUNDER_CERTIFICATIONS
    )

    skills = tuple(
        SkillRecord(f"skill-{_skill_slug(name)}", name, (f"ev-skill-{_skill_slug(name)}",))
        for name in _FOUNDER_SKILLS
    )

    return CareerProfile(
        id="career-founder-shaped",
        evidence_ids=("ev-founder-profile",),
        employment=employment,
        education=(
            EducationRecord(
                "education-founder-shaped", "Nile Institute", "BSc in Computer Science",
                date(2013, 9, 1), date(2017, 6, 30), ("ev-founder-education",),
            ),
        ),
        certifications=certifications,
        skills=skills,
        languages=(
            LanguageRecord("language-founder-en", "English", "professional", ("ev-founder-language-en",)),
            LanguageRecord("language-founder-ar", "Arabic", "native", ("ev-founder-language-ar",)),
        ),
        work_authorizations=(
            WorkAuthorization("auth-founder-egypt", "Egypt", "authorized", ("ev-founder-work-auth",)),
        ),
        approved_summaries=("Data engineer with group-scale platform experience across freight and logistics data.",),
        red_lines=(
            RedLineRule(
                "red-founder-guarantee",
                r"\b(?:guarantee\w*|100%\s*(?:success|satisfaction|result|roi)|unconditional\w*\s*(?:promise\w*|assur\w*)|zero\s*risk|assure\w*\s*(?:positive\s*)?(?:outcome|roi|results?)|promis\w*\s*(?:positive\s*)?(?:success|results?|outcome))\b",
                "outcomes cannot be guaranteed",
            ),
        ),
        never_claims=(
            NeverClaimRule(
                "never-founder-guarantee",
                ProhibitedConceptCategory.GUARANTEED_OUTCOME,
                "outcomes cannot be guaranteed",
                r"\b(?:guarantee\w*|100%\s*(?:success|satisfaction|result|roi)|unconditional\w*\s*(?:promise\w*|assur\w*)|zero\s*risk|assure\w*\s*(?:positive\s*)?(?:outcome|roi|results?)|promis\w*\s*(?:positive\s*)?(?:success|results?|outcome))\b",
                ("guarantee", "100% success"),
            ),
            NeverClaimRule(
                "never-founder-f500",
                ProhibitedConceptCategory.FORTUNE_500_PRESTIGE,
                "no client evidence exists",
                r"\b(?:fortune\s*500|global\s*2000|f500|top\s*fortune)\b",
                ("Fortune 500 clients", "Fortune 500"),
            ),
        ),
    )


def founder_shaped_capability_profile() -> CapabilityProfile:
    return CapabilityProfile(
        id="capability-founder-shaped",
        evidence_ids=("ev-founder-cap-profile",),
        services=(
            ServiceRecord(
                "service-founder-platform", "Group data platform advisory",
                "Offers group data platform advisory with Fixed price and Consultant tender engagement models "
                "delivering Evidence-backed findings and Prioritized remediation plan.",
                ("ev-founder-service-platform",),
                (EngagementType.FIXED_PRICE, EngagementType.CONSULTANT_TENDER),
                ("Evidence-backed findings", "Prioritized remediation plan"),
            ),
            ServiceRecord(
                "service-founder-etl", "ETL pipeline assessment",
                "Offers ETL pipeline assessment with Time and materials and Retainer engagement models "
                "delivering Evidence-backed findings and Prioritized remediation plan.",
                ("ev-founder-service-etl",),
                (EngagementType.TIME_AND_MATERIALS, EngagementType.RETAINER),
                ("Evidence-backed findings", "Prioritized remediation plan"),
            ),
        ),
        portfolio=(
            PortfolioItem(
                "portfolio-founder-group", "Shared data platform migration",
                "Delivered a shared data platform migration for a multi-subsidiary freight group.",
                ("ev-founder-portfolio-group",),
            ),
            PortfolioItem(
                "portfolio-founder-etl", "ETL pipeline reliability review",
                "Delivered an ETL pipeline reliability review for a regional logistics operator.",
                ("ev-founder-portfolio-etl",),
            ),
        ),
        capacity=BusinessCapacity(
            "capacity-founder-shaped", ("ev-founder-capacity",),
            available_from=date(2026, 10, 2), hours_per_week=25,
            min_project_value=2000, max_project_value=20000, currencies=("USD",),
            service_regions=("MENA", "WORLDWIDE"), onsite_willingness="case_by_case",
        ),
        target_industries=("Logistics", "Technology"),
        excluded_industries=("Weapons",),
        delivery_languages=("English",),
    )


def founder_shaped_graph() -> TruthGraph:
    metrics = tuple(
        MetricAssertion(
            id=f"metric-{role['rid']}",
            subject_id=f"achievement-{role['rid']}",
            numeric_value=role["metric"][0],
            unit=role["metric"][1],
            # Deliberately keeps its natural trailing period (this achievement
            # sentence, like a real founder's, ends in one): the compiler
            # itself now strips it before building "{context}: {value}{unit}"
            # (`matching/compiler_employment.py`, BRIEF-FR-005 D1
            # remediation). A real founder's truth pack passes a YAML
            # `context` string through ingest verbatim, almost always as a
            # full, period-terminated sentence -- this field is written this
            # way specifically to exercise that real, non-hypothetical
            # exposure, not as a fixture-only style choice.
            context=role["achievement"],
            verification_status=MetricVerification.VERIFIED,
            evidence_ids=(f"ev-{role['rid']}-achievement",),
        )
        for role in _FOUNDER_ROLES
        if "metric" in role
    )
    graph = TruthGraph(founder_shaped_evidence(), metrics=metrics)
    graph.add_career_profile(founder_shaped_career_profile())
    graph.add_capability_profile(founder_shaped_capability_profile())

    preference_assertions = (
        AtomicAssertion(
            id="as-founder-pref-target-role",
            subject_id="career-founder-shaped",
            predicate="career.target_role",
            value="Data Engineer",
            evidence_ids=("ev-founder-pref-target-role",),
        ),
        AtomicAssertion(
            id="as-founder-pref-track",
            subject_id="career-founder-shaped",
            predicate="preference.track",
            value="employment",
            evidence_ids=("ev-founder-pref-track",),
        ),
        AtomicAssertion(
            id="as-founder-pref-goal",
            subject_id="career-founder-shaped",
            predicate="career.goal",
            value="lead a shared data platform for a distributed engineering group",
            evidence_ids=("ev-founder-pref-goal",),
        ),
        AtomicAssertion(
            id="as-founder-pref-residence",
            subject_id="career-founder-shaped",
            predicate="residence.country",
            value="Egypt",
            evidence_ids=("ev-founder-pref-residence",),
        ),
        AtomicAssertion(
            id="as-founder-pref-premium",
            subject_id="career-founder-shaped",
            predicate="preference.fulltime_onsite_premium_monthly",
            value=50000,
            evidence_ids=("ev-founder-pref-premium",),
        ),
    )
    for assertion in preference_assertions:
        graph.add_assertion(assertion)

    graph.add_identity(founder_shaped_identity())
    for phrase in founder_shaped_approved_phrases():
        graph.add_approved_phrase(phrase)

    return graph
