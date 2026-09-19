"""Deterministic selector for the Founder-locked six-CV portfolio.

Production employment applications select one immutable, pre-approved PDF.
OpportunityOS must never synthesize or rewrite a CV for a posting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
    CVVariant("ai_engineer", "Mohammed_Ehab_AI_Engineer_CV_2026.pdf", "2026/Mohammed_Ehab_AI_Engineer_CV_2026.pdf", "24e84bbaf4cd7aaff59bcbbedefa3db3f3b673c19b9913b3ff7a9283dab01c52"),
    CVVariant("business_analyst", "Mohammed_Ehab_Business_Analyst_CV_2026.pdf", "2026/Mohammed_Ehab_Business_Analyst_CV_2026.pdf", "1ef4a990b081b1c07ddce26cd28cc99e6058e39d8b9c06dea58c8f0858a65301"),
    CVVariant("data_analyst", "Mohammed_Ehab_Data_Analyst_CV_2026.pdf", "2026/Mohammed_Ehab_Data_Analyst_CV_2026.pdf", "9d8c99bd46fe82200b286ac7901e69f533d5d2a0f7e59393d8f98f2996bd058d"),
    CVVariant("data_engineer", "Mohammed_Ehab_Data_Engineer_CV_2026.pdf", "2026/Mohammed_Ehab_Data_Engineer_CV_2026.pdf", "9a01666790f34ed16aea8ebd7c414411f6d7ee4a8cf7fcc3ed5edd1866867516"),
    CVVariant("data_scientist", "Mohammed_Ehab_Data_Scientist_CV_2026.pdf", "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", "d80953e57ea61d676001618b37ae73beb225659ad1835ee779500aa2bb470398"),
    CVVariant("master", "Mohammed_Ehab_Master_CV_2026.pdf", "2026/Mohammed_Ehab_Master_CV_2026.pdf", "4b52a32e58008afd59a93ebdf9edc5b165a624a7e4f2cd13eefadf009a44b7d5"),
)
_BY_VARIANT = {item.variant: item for item in PORTFOLIO}

TITLE_PHRASES: dict[str, tuple[str, ...]] = {
    "data_engineer": (
        "data engineer", "data migration engineer", "data integration engineer",
        "etl engineer", "analytics engineer", "data platform engineer",
    ),
    "data_scientist": (
        "data scientist", "applied scientist", "machine learning scientist",
        "ml scientist", "research scientist",
    ),
    "data_analyst": (
        "data analyst", "bi analyst", "business intelligence analyst",
        "reporting analyst", "analytics analyst",
    ),
    "business_analyst": (
        "business analyst", "business systems analyst", "technical business analyst",
        "data business analyst", "functional analyst",
    ),
    "ai_engineer": (
        "ai engineer", "artificial intelligence engineer", "generative ai engineer",
        "llm engineer", "rag engineer", "applied ai engineer", "ai application engineer",
        "machine learning engineer",
    ),
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_engineer": (
        "etl", "elt", "data pipeline", "data pipelines", "data migration", "data integration",
        "source-to-target", "databricks", "spark", "warehouse", "lakehouse", "orchestration",
        "data quality", "reconciliation", "postgresql",
    ),
    "data_scientist": (
        "statistics", "statistical", "predictive modeling", "forecasting", "experiment",
        "experimentation", "model calibration", "machine learning", "deep learning",
        "scikit-learn", "tensorflow", "pytorch", "monte carlo", "nlp",
    ),
    "data_analyst": (
        "power bi", "dashboard", "dashboards", "excel", "kpi", "reporting", "visualization",
        "data visualization", "business intelligence", "trend analysis", "analytics",
    ),
    "business_analyst": (
        "requirements gathering", "business requirements", "functional requirements",
        "stakeholder", "stakeholders", "process mapping", "business process", "uat",
        "user acceptance testing", "brd", "specifications", "decision support",
    ),
    "ai_engineer": (
        "generative ai", "llm", "large language model", "rag", "retrieval-augmented",
        "agent", "agents", "multi-agent", "prompt", "tool calling", "embeddings",
        "vector", "fastapi", "ai application", "conversational",
    ),
}

ML_PLATFORM_TERMS = (
    "mlops", "feature store", "model serving platform", "training pipeline",
    "data pipeline", "spark", "databricks", "airflow", "orchestration",
)
ML_APPLICATION_TERMS = (
    "llm", "generative ai", "rag", "agent", "agents", "prompt", "tool calling",
    "embeddings", "conversational ai",
)
ML_SCIENCE_TERMS = (
    "statistics", "experimentation", "predictive", "forecasting", "modeling",
    "model calibration", "research", "scikit-learn", "tensorflow", "pytorch",
)


def _norm(text: str) -> str:
    return " ".join((text or "").casefold().replace("/", " ").replace("-", " ").split())


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


def _score_variant(variant: str, title: str, body: str, skills: tuple[str, ...]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for phrase in TITLE_PHRASES.get(variant, ()):
        if _contains(title, phrase):
            score += 12
            reasons.append(f"title:{phrase}")
    for keyword in KEYWORDS.get(variant, ()):
        if _contains(body, keyword):
            score += 2
        if any(_contains(skill, keyword) or _contains(keyword, skill) for skill in skills if skill):
            score += 3
    return score, reasons


def _machine_learning_engineer_override(title: str, body: str, skills: tuple[str, ...]) -> str | None:
    if "machine learning engineer" not in title and "ml engineer" not in title:
        return None
    corpus = " ".join((body, *skills))
    app = sum(1 for term in ML_APPLICATION_TERMS if _contains(corpus, term))
    platform = sum(1 for term in ML_PLATFORM_TERMS if _contains(corpus, term))
    science = sum(1 for term in ML_SCIENCE_TERMS if _contains(corpus, term))
    if app > max(platform, science):
        return "ai_engineer"
    if platform > max(app, science):
        return "data_engineer"
    return "data_scientist"


def select_cv_for_opportunity(opp: Opportunity) -> CVSelection:
    """Select one immutable CV variant for an employment opportunity.

    No generated text is returned. The selected filename/hash identifies the
    exact Founder-approved PDF bytes that the delivery layer must retrieve.
    """
    if opp.track != Track.EMPLOYMENT:
        raise ValueError("fixed CV portfolio selection is employment-only")

    title, body, skills = _full_text(opp)

    ml_override = _machine_learning_engineer_override(title, body, skills)
    if ml_override is not None:
        scores = []
        for variant in ("ai_engineer", "business_analyst", "data_analyst", "data_engineer", "data_scientist"):
            score, _ = _score_variant(variant, title, body, skills)
            scores.append((variant, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        return CVSelection(
            selected=_BY_VARIANT[ml_override],
            scores=tuple(scores),
            reasons=(f"machine-learning-engineer specialization -> {ml_override}",),
        )

    scored: list[tuple[str, int, list[str]]] = []
    for variant in ("ai_engineer", "business_analyst", "data_analyst", "data_engineer", "data_scientist"):
        score, reasons = _score_variant(variant, title, body, skills)
        scored.append((variant, score, reasons))

    scored.sort(key=lambda item: (-item[1], item[0]))
    best_variant, best_score, best_reasons = scored[0]
    second_score = scored[1][1]

    # Specialist selection requires a meaningful signal and a clear lead.
    if best_score < 8 or best_score == second_score:
        selected = _BY_VARIANT["master"]
        reasons = ("no specialist variant clearly dominates -> master",)
    else:
        selected = _BY_VARIANT[best_variant]
        reasons = tuple(best_reasons) or (f"keyword fit -> {best_variant}",)

    return CVSelection(
        selected=selected,
        scores=tuple((variant, score) for variant, score, _ in scored),
        reasons=reasons,
    )


def portfolio_hashes() -> dict[str, str]:
    """Expected SHA-256 by filename; useful for upload/runtime integrity checks."""
    return {item.filename: item.sha256 for item in PORTFOLIO}
