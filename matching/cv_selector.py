"""Deterministic selector for the Founder-locked nine-CV portfolio.

Production employment applications select one immutable, pre-approved PDF.
OpportunityOS must never synthesize or rewrite a CV for a posting.
"""
from __future__ import annotations

from dataclasses import dataclass

from opportunity.models import Opportunity, Track


@dataclass(frozen=True, slots=True)
class CVVariant:
    variant: str
    filename: str
    object_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CVSelection:
    selected: CVVariant
    scores: tuple[tuple[str, int], ...]
    reasons: tuple[str, ...]


PORTFOLIO: tuple[CVVariant, ...] = (
    CVVariant(
        "ai_engineer",
        "Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf",
        "2026/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf",
        "d4de3d8a5a634000fe4f4fc880fddbdf9f049653486244b1249b86dec4de651d",
    ),
    CVVariant(
        "business_analyst",
        "Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf",
        "2026/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf",
        "63142654468062da55dfe5821127ce80547915205ca52eb2a413a2bea6e42f3c",
    ),
    CVVariant(
        "data_analyst",
        "Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf",
        "2026/Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf",
        "56558cb5c618be45b0261ac9730a13f38088d50ff6869dba9a257e00cd8326a9",
    ),
    CVVariant(
        "data_engineer",
        "Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf",
        "2026/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf",
        "80fe24c23364efe94525147609e1c70554d2347e06d11632015fd7095789a405",
    ),
    CVVariant(
        "data_scientist",
        "Mohammed_Ehab_Data_Scientist_CV_2026.pdf",
        "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf",
        "d6d7119d908eb05ce30e0d6b95a2a555c03828ab1be98c94fbd9bcd0158daebd",
    ),
    CVVariant(
        "ml_engineer",
        "Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf",
        "2026/Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf",
        "b705a4cc85ad7aca72de8f2832b250e579bdb5e92a5c0f77b87e6971471058e3",
    ),
    CVVariant(
        "solutions_engineer",
        "Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.pdf",
        "2026/Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.pdf",
        "41a1a54342a9c1db091ffce7c68f2755ee3c51a8ea33abfa153e73b07b1ffd87",
    ),
    CVVariant(
        "fullstack_product",
        "Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.pdf",
        "2026/Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.pdf",
        "5b01d3bfb83bc90a67902f668499d42fa33146928bc6a1f05b29c760999ebf60",
    ),
    CVVariant(
        "master",
        "Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf",
        "2026/Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf",
        "f20ceec79d450f66d241640f36fbcbac74ee2d365da7e29e4d11883c352e5407",
    ),
)
_BY_VARIANT = {item.variant: item for item in PORTFOLIO}
_SPECIALIST_VARIANTS = tuple(item.variant for item in PORTFOLIO if item.variant != "master")

# Canonical aliases from OpportunityOS_CV_Registry.json in the Founder-approved
# 2026-09-21 final pack. Keep title routing narrow and let responsibilities /
# requirements / listed skills break ambiguous titles.
TITLE_PHRASES: dict[str, tuple[str, ...]] = {
    "data_engineer": (
        "data engineer",
        "data integration engineer",
        "etl engineer",
        "etl developer",
        "data migration engineer",
        "data implementation engineer",
        "implementation engineer",
        "data platform engineer",
    ),
    "data_analyst": (
        "data analyst",
        "bi analyst",
        "business intelligence analyst",
        "bi developer",
        "reporting analyst",
        "operations analyst",
        "supply chain analyst",
        "marketing analyst",
    ),
    "data_scientist": (
        "data scientist",
        "applied data scientist",
        "decision scientist",
        "statistical data scientist",
        "geospatial data scientist",
    ),
    "ml_engineer": (
        "machine learning engineer",
        "ml engineer",
        "applied ml engineer",
        "computer vision engineer",
        "geospatial ml engineer",
        "production ml engineer",
    ),
    "ai_engineer": (
        "ai engineer",
        "applied ai engineer",
        "llm engineer",
        "generative ai engineer",
        "rag engineer",
        "ai automation engineer",
        "agent engineer",
    ),
    "business_analyst": (
        "business analyst",
        "technical business analyst",
        "it business analyst",
        "systems analyst",
        "business systems analyst",
        "product analyst",
        "digital business analyst",
    ),
    "solutions_engineer": (
        "ai solutions engineer",
        "solutions engineer",
        "technical solutions engineer",
        "solutions consultant",
        "technical consultant",
        "ai data consultant",
        "implementation consultant",
    ),
    "fullstack_product": (
        "full stack engineer",
        "fullstack engineer",
        "product engineer",
        "python react engineer",
        "technical product engineer",
    ),
}

# Job-side relevance vocabulary. These terms route to an already-approved CV;
# they never add claims to the CV itself.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_engineer": (
        "etl", "elt", "data pipeline", "data pipelines", "data integration",
        "data migration", "source to target", "mapping", "transformation",
        "data profiling", "cleansing", "validation", "reconciliation",
        "data quality", "databricks", "pyspark", "postgresql", "sqlalchemy",
        "alembic", "supabase",
    ),
    "data_analyst": (
        "data analysis", "power bi", "dashboard", "dashboards", "excel",
        "kpi", "reporting", "data visualization", "business intelligence",
        "trend analysis", "operations analytics", "supply chain analytics",
        "marketing analytics", "sql",
    ),
    "data_scientist": (
        "statistical modeling", "probabilistic modeling", "predictive modeling",
        "feature engineering", "supervised learning", "unsupervised learning",
        "classification", "forecasting", "model evaluation", "calibration",
        "backtesting", "monte carlo", "data science", "scikit learn",
        "geospatial analytics",
    ),
    "ml_engineer": (
        "machine learning", "deep learning", "computer vision", "model training",
        "model pipeline", "model serving", "onnx", "mlflow", "pytorch",
        "tensorflow", "transformers", "fastapi", "docker", "inference",
        "experiment tracking",
    ),
    "ai_engineer": (
        "llm", "large language model", "generative ai", "rag",
        "retrieval augmented", "embeddings", "retrieval", "agent", "agents",
        "prompt", "tool calling", "conversational", "knowledge grounding",
        "ai evaluation", "ai automation", "fastapi",
    ),
    "business_analyst": (
        "requirements gathering", "business requirements", "stakeholder",
        "business process", "kpi definition", "reporting", "data mapping",
        "functional validation", "technical translation", "product requirements",
        "cross functional delivery", "systems analysis",
    ),
    "solutions_engineer": (
        "technical discovery", "solution design", "api integration",
        "data integration", "prototyping", "technical consulting",
        "implementation planning", "production readiness", "stakeholder",
        "solution architecture", "ai architecture", "data architecture",
    ),
    "fullstack_product": (
        "full stack", "frontend", "backend", "rest api", "rest apis",
        "database design", "product architecture", "next.js", "nextjs",
        "react", "typescript", "fastapi", "postgresql", "docker",
        "ecommerce", "payments", "deployment", "ci cd", "playwright",
    ),
}


def _norm(text: str) -> str:
    return " ".join(
        (text or "")
        .casefold()
        .replace("/", " ")
        .replace("-", " ")
        .replace("&", " and ")
        .split()
    )


def _contains(text: str, phrase: str) -> bool:
    return _norm(phrase) in text


def _full_text(opp: Opportunity) -> tuple[str, str, tuple[str, ...]]:
    title = _norm(opp.title)
    body_parts: list[str] = [opp.description]
    body_parts.extend(opp.responsibilities)
    body_parts.extend(opp.requirements)
    body = _norm(" ".join(body_parts))
    skills = tuple(_norm(s) for s in opp.skills)
    return title, body, skills


def _score_variant(
    variant: str,
    title: str,
    body: str,
    skills: tuple[str, ...],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    for phrase in TITLE_PHRASES.get(variant, ()):
        if _contains(title, phrase):
            score += 12
            reasons.append(f"title:{phrase}")

    for keyword in KEYWORDS.get(variant, ()):
        if _contains(body, keyword):
            score += 2
        if any(
            _contains(skill, keyword) or _contains(keyword, skill)
            for skill in skills
            if skill
        ):
            score += 3

    return score, reasons


def select_cv_for_opportunity(opp: Opportunity) -> CVSelection:
    """Select one immutable Founder-approved CV for an employment opportunity.

    The 2026-09-21 final system contains eight targeted role families plus one
    Master Comprehensive fallback. No generated text is returned: the selected
    filename/hash identifies the exact PDF bytes the delivery layer retrieves.
    """
    if opp.track != Track.EMPLOYMENT:
        raise ValueError("fixed CV portfolio selection is employment-only")

    title, body, skills = _full_text(opp)

    scored: list[tuple[str, int, list[str]]] = []
    for variant in _SPECIALIST_VARIANTS:
        score, reasons = _score_variant(variant, title, body, skills)
        scored.append((variant, score, reasons))

    scored.sort(key=lambda item: (-item[1], item[0]))
    best_variant, best_score, best_reasons = scored[0]
    second_score = scored[1][1]

    # Specialist selection requires a meaningful signal and a clear lead.
    # A direct canonical title match is 12 points by itself.
    if best_score < 8 or best_score == second_score:
        selected = _BY_VARIANT["master"]
        reasons = ("no specialist variant clearly dominates -> master",)
    else:
        selected = _BY_VARIANT[best_variant]
        reasons = tuple(best_reasons) or (f"responsibility/skill fit -> {best_variant}",)

    return CVSelection(
        selected=selected,
        scores=tuple((variant, score) for variant, score, _ in scored),
        reasons=reasons,
    )


def portfolio_hashes() -> dict[str, str]:
    """Expected SHA-256 by filename for upload/runtime integrity checks."""
    return {item.filename: item.sha256 for item in PORTFOLIO}
