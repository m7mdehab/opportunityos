"""Synthetic, non-PII fixtures and gold claims for the truth engine."""

from __future__ import annotations

from datetime import date

from .graph import TruthGraph
from .models import (
    Achievement,
    AssertionType,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    CertificationRecord,
    CertificationState,
    EducationRecord,
    EmploymentRecord,
    EngagementType,
    EvidenceRecord,
    LanguageRecord,
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
        EvidenceRecord("ev-org", "Synthetic Analytics Ltd", "synthetic_cv", "employment.0.organization"),
        EvidenceRecord("ev-title", "Data Engineer", "synthetic_cv", "employment.0.title"),
        EvidenceRecord("ev-dates", "2022-01-01 to 2024-06-30", "synthetic_cv", "employment.0.dates"),
        EvidenceRecord(
            "ev-achievement",
            "Built a synthetic reporting pipeline that reduced processing time by 40%.",
            "synthetic_cv", "employment.0.achievements.0",
        ),
        EvidenceRecord(
            "ev-python", "Uses Python for data engineering.", "synthetic_cv", "skills.0",
            assertion_type=AssertionType.NORMALIZED_FACT,
        ),
        EvidenceRecord("ev-degree", "BSc in Example Systems from Example Institute from 2017-09-01 to 2021-06-30.", "synthetic_cv", "education.0"),
        EvidenceRecord("ev-language", "English professional proficiency", "synthetic_cv", "languages.0"),
        EvidenceRecord("ev-work-auth", "Authorized to work in Exampleland", "synthetic_cv", "work_authorizations.0"),
        EvidenceRecord(
            "ev-cert-plan", "Planning to pursue the Example Cloud Architect certification from Example Cloud Foundation.",
            "synthetic_profile", "certifications.0",
        ),
        EvidenceRecord(
            "ev-service", "Offers analytics pipeline assessments and deliverables including Evidence-backed findings and Prioritized remediation plan.",
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
    )


def synthetic_career_profile() -> CareerProfile:
    return CareerProfile(
        id="career-synthetic",
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
        skills=(SkillRecord("skill-python", "Python", ("ev-python",), "advanced"),),
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
        services=(
            ServiceRecord(
                "service-assessment", "Analytics pipeline assessment",
                "Offers analytics pipeline assessments.", ("ev-service",),
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
    graph = TruthGraph(synthetic_evidence())
    graph.add_career_profile(synthetic_career_profile())
    graph.add_capability_profile(synthetic_capability_profile())
    return graph
