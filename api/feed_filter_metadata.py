"""Count-only metadata for the SQL-native founder feed filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, func, literal, or_
from sqlalchemy.orm import Session

from storage.feed_projection import FeedProjectionRecord
from storage.feed_query import FEED_SORTS
from storage.models import FounderActivityEventRecord, FounderFeedbackRecord

UNKNOWN = "unknown"
MAX_FACET_VALUES = 100


@dataclass(frozen=True)
class CategoryFacet:
    key: str
    column: Any
    normalize_case: bool = True
    unknown_aliases: tuple[str, ...] = ()
    single_select: bool = False


CATEGORY_FACETS = (
    CategoryFacet("track", FeedProjectionRecord.track, normalize_case=False),
    CategoryFacet("decision", FeedProjectionRecord.qualification_decision),
    CategoryFacet("work_mode", FeedProjectionRecord.work_mode),
    CategoryFacet("location_country", FeedProjectionRecord.location_country),
    CategoryFacet("location_city", FeedProjectionRecord.location_city),
    CategoryFacet("remote_scope", FeedProjectionRecord.remote_scope),
    CategoryFacet("employment_type", FeedProjectionRecord.employment_type),
    CategoryFacet("seniority_level", FeedProjectionRecord.seniority_level),
    CategoryFacet("target_tier", FeedProjectionRecord.target_tier),
    CategoryFacet("title_family", FeedProjectionRecord.title_family, unknown_aliases=("other",)),
    CategoryFacet("source_id", FeedProjectionRecord.source_id),
)

EVENT_FACETS = (
    ("feedback_label", FounderFeedbackRecord, FounderFeedbackRecord.feedback_label),
    ("activity_type", FounderActivityEventRecord, FounderActivityEventRecord.action_type),
)

SCORE_COLUMNS = (
    ("fit_score", FeedProjectionRecord.fit_score),
    ("preference_score", FeedProjectionRecord.preference_score),
    ("confidence_score", FeedProjectionRecord.confidence_score),
    ("priority_score", FeedProjectionRecord.priority_score),
)
SCORE_THRESHOLDS = (90, 80, 70, 60, 50)

SORT_LABELS = {
    "recommended": "Recommended",
    "fit_desc": "Fit Score — Highest first",
    "fit_asc": "Fit Score — Lowest first",
    "newest_posted": "Newest posted",
    "oldest_posted": "Oldest posted",
    "remote_first": "Remote first",
}

# These are explicit capability gaps from FR-008 §7. Their reasons describe
# the current persisted query contract; they do not enable or apply filters.
UNAVAILABLE_FILTERS = (
    {
        "id": "tracking_state",
        "label": "Tracking state",
        "reason": "Saved, snoozed, dismissed, applied, and submitted state combinations are not part of the W5.1 feed-filter contract.",
    },
    {
        "id": "eligibility_evidence",
        "label": "Eligibility evidence",
        "reason": "Qualification decision is available; explicit restriction, sponsorship, and work-authorization evidence is not a queryable projection field.",
    },
    {
        "id": "title_level_and_keywords",
        "label": "Title level and exact title keywords",
        "reason": "Title level and exact title-keyword filters are not exposed by the W5.1 query contract. General text search remains available separately.",
    },
    {
        "id": "location_region",
        "label": "Location regions",
        "reason": "Region text is stored as source-native text and is not normalized into exact selectable region values.",
    },
    {
        "id": "skill_match_and_gaps",
        "label": "Skill match and gaps",
        "reason": "Required, matched, missing, and preferred skills are not persisted as structured per-opportunity query fields.",
    },
    {
        "id": "experience_responsibility",
        "label": "Experience and responsibility",
        "reason": "Years-of-experience and responsibility-level evidence is not persisted in the feed projection query contract.",
    },
    {
        "id": "work_authorization_relocation",
        "label": "Work authorization and relocation",
        "reason": "Job-side authorization, sponsorship, relocation, and on-site cadence evidence is not exposed as queryable projection fields.",
    },
    {
        "id": "compensation",
        "label": "Compensation ranges",
        "reason": "Compensation provenance exists outside the feed-query projection, without normalized comparable amount, currency, and pay-period fields.",
    },
    {
        "id": "company_attributes",
        "label": "Company attributes",
        "reason": "Industry, size, stage, ownership, funding, and employer-name filters are not exposed as normalized W5.1 query dimensions.",
    },
    {
        "id": "source_taxonomy_and_health",
        "label": "Source family, ATS, and source health",
        "reason": "Source ID is queryable; source family, ATS type, source quality, polling health, and error-rate dimensions are not normalized in the feed contract.",
    },
    {
        "id": "posting_health",
        "label": "Posting freshness and health",
        "reason": "Posted-date bounds are queryable; deadline, discovery time, stale/reverified state, and duplicate/closed health signals are not persisted in this query contract.",
    },
    {
        "id": "content_completeness",
        "label": "Content completeness",
        "reason": "Description presence, description length, structured-field coverage, and extraction-confidence flags are not queryable projection fields.",
    },
    {
        "id": "education_certification",
        "label": "Education and certification",
        "reason": "Degree, education-level, and certification requirements are not persisted as structured feed-query fields.",
    },
    {
        "id": "language_timezone_travel",
        "label": "Language, time zone, and travel",
        "reason": "Language, working-hour overlap, time-zone, and travel requirements are not persisted as structured feed-query fields.",
    },
    {
        "id": "cv_application_readiness",
        "label": "CV and application readiness",
        "reason": "Canonical CV selection and application-artifact readiness are user/tracker concerns outside the W5.1 opportunity query dimensions.",
    },
    {
        "id": "tracked_user_metadata",
        "label": "Tracked-job user metadata",
        "reason": "Notes, follow-up dates, application status, and user-defined tags are tracker metadata and are not part of the feed projection.",
    },
)


def _visible_truth_filter(truth_pack_hash: str):
    return (
        FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
        FeedProjectionRecord.visible.is_(True),
    )


def _bucket_expression(facet: CategoryFacet):
    column = facet.column
    trimmed = func.trim(column)
    normalized = func.lower(trimmed) if facet.normalize_case else trimmed
    unknown_conditions = [column.is_(None), trimmed == ""]
    unknown_conditions.append(func.lower(trimmed) == UNKNOWN)
    if facet.unknown_aliases:
        unknown_conditions.append(func.lower(trimmed).in_(facet.unknown_aliases))
    return case(
        (or_(*unknown_conditions), literal(UNKNOWN)),
        else_=normalized,
    )


def _category_statement(facet: CategoryFacet, truth_pack_hash: str):
    bucket = _bucket_expression(facet)
    return (
        FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
        FeedProjectionRecord.visible.is_(True),
    ), bucket


def _category_query(session: Session, facet: CategoryFacet, truth_pack_hash: str):
    predicates, bucket = _category_statement(facet, truth_pack_hash)
    return (
        session.query(
            bucket.label("value"),
            func.count().label("row_count"),
            func.count().over().label("option_count"),
        )
        .filter(*predicates)
        .group_by(bucket)
        .order_by(func.count().desc(), bucket.asc())
        .limit(MAX_FACET_VALUES)
    )


def _category_payload(session: Session, facet: CategoryFacet, truth_pack_hash: str) -> dict[str, Any]:
    rows = _category_query(session, facet, truth_pack_hash).all()
    option_count = int(rows[0].option_count) if rows else 0
    return {
        "selection": "single" if facet.single_select else "multiple",
        "values": [
            {"value": str(row.value), "count": int(row.row_count)}
            for row in rows
        ],
        "option_count": option_count,
        "truncated": option_count > MAX_FACET_VALUES,
    }


def _score_statement(truth_pack_hash: str):
    expressions = []
    for key, column in SCORE_COLUMNS:
        expressions.extend((
            func.min(column).label(f"{key}_min"),
            func.max(column).label(f"{key}_max"),
            func.sum(case((column.is_(None), 1), else_=0)).label(f"{key}_unknown"),
        ))
        for threshold in SCORE_THRESHOLDS:
            expressions.append(
                func.sum(case((column >= threshold, 1), else_=0)).label(f"{key}_gte_{threshold}")
            )
    return (
        expressions,
        _visible_truth_filter(truth_pack_hash),
    )


def _score_query(session: Session, truth_pack_hash: str):
    expressions, predicates = _score_statement(truth_pack_hash)
    return session.query(*expressions).filter(*predicates)


def _date_statement(truth_pack_hash: str):
    date_value = func.nullif(func.trim(FeedProjectionRecord.posted_date), "")
    unknown_count = func.sum(case((date_value.is_(None), 1), else_=0))
    return (
        date_value.label("posted_min"),
        func.max(date_value).label("posted_max"),
        unknown_count.label("posted_unknown"),
    ), _visible_truth_filter(truth_pack_hash)


def _date_query(session: Session, truth_pack_hash: str):
    expressions, predicates = _date_statement(truth_pack_hash)
    return session.query(*expressions).filter(*predicates)


def _score_payload(session: Session, truth_pack_hash: str) -> dict[str, Any]:
    row = _score_query(session, truth_pack_hash).one()
    ranges: dict[str, Any] = {}
    for key, _column in SCORE_COLUMNS:
        ranges[key] = {
            "min": getattr(row, f"{key}_min"),
            "max": getattr(row, f"{key}_max"),
            "unknown_count": int(getattr(row, f"{key}_unknown") or 0),
            "threshold_counts": {
                f"{threshold}+": int(getattr(row, f"{key}_gte_{threshold}") or 0)
                for threshold in SCORE_THRESHOLDS
            },
        }
    return ranges


def _date_payload(session: Session, truth_pack_hash: str) -> dict[str, Any]:
    row = _date_query(session, truth_pack_hash).one()
    return {
        "min": row.posted_min,
        "max": row.posted_max,
        "unknown_count": int(row.posted_unknown or 0),
    }


def _event_facet_payload(session: Session, truth_pack_hash: str, model, column) -> dict[str, Any]:
    rows = (
        session.query(column, func.count(func.distinct(model.opportunity_id)))
        .join(FeedProjectionRecord, FeedProjectionRecord.opportunity_id == model.opportunity_id)
        .filter(*_visible_truth_filter(truth_pack_hash))
        .group_by(column)
        .order_by(column.asc())
        .limit(MAX_FACET_VALUES + 1)
        .all()
    )
    return {
        "selection": "multiple",
        "values": [{"value": value, "count": int(count)} for value, count in rows[:MAX_FACET_VALUES]],
        "option_count": len(rows),
        "truncated": len(rows) > MAX_FACET_VALUES,
    }


def feed_filter_metadata(session: Session, truth_pack_hash: str) -> dict[str, Any]:
    """Return bounded option counts and capability gaps for visible projections.

    Counts are scoped to one truth-pack's visible rows, before interactive
    feed selections and tracked/ineligible exclusions. Only grouped scalar
    values and aggregate statistics leave the database.
    """
    facets = {
        facet.key: _category_payload(session, facet, truth_pack_hash)
        for facet in CATEGORY_FACETS
    }
    for key, model, column in EVENT_FACETS:
        facets[key] = _event_facet_payload(session, truth_pack_hash, model, column)
    return {
        "truth_pack_hash": truth_pack_hash,
        "count_scope": {
            "visible_only": True,
            "independent_of_selected_filters": True,
            "includes_tracked_and_ineligible": True,
        },
        "facets": facets,
        "ranges": {
            **_score_payload(session, truth_pack_hash),
            "posted_date": _date_payload(session, truth_pack_hash),
        },
        "sorts": [
            {"value": key, "label": SORT_LABELS[key]}
            for key in SORT_LABELS
            if key in FEED_SORTS
        ],
        "unavailable_filters": [dict(item) for item in UNAVAILABLE_FILTERS],
    }
