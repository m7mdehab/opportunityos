from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import case, exists, func, literal_column, not_, or_
from sqlalchemy.orm import Query, Session

from outbound.models import ActionStatus
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    FounderActivityEventRecord,
    FounderFeedbackRecord,
    FounderTriageStateRecord,
    OutboundActionRecordModel,
)

UNKNOWN_FILTER_VALUE = "unknown"
FEED_SORTS = frozenset({
    "recommended",
    "fit_desc",
    "fit_asc",
    "newest_posted",
    "oldest_posted",
    "remote_first",
})


@dataclass(frozen=True)
class FeedQuerySpec:
    """Database-native founder feed query contract.

    The request path is intentionally constrained to persisted projection
    columns.  It must never reach back into OpportunityRecord descriptions or
    rebuild matching/filter contexts across the corpus.
    """

    truth_pack_hash: str
    track: str | None = None
    decision: str | None = None
    track_values: tuple[str, ...] = ()
    decision_values: tuple[str, ...] = ()
    feedback_labels: tuple[str, ...] = ()
    activity_types: tuple[str, ...] = ()
    min_score: float | None = None
    max_score: float | None = None
    since: str | None = None
    work_mode: str | None = None
    location_country: str | None = None
    title_family: str | None = None
    source_id: str | None = None
    q: str | None = None
    include_hidden: bool = False
    include_tracked: bool = False
    as_of: datetime | None = None
    page: int = 1
    page_size: int = 25
    work_modes: tuple[str, ...] = ()
    location_countries: tuple[str, ...] = ()
    location_cities: tuple[str, ...] = ()
    remote_scopes: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    seniority_levels: tuple[str, ...] = ()
    target_tiers: tuple[str, ...] = ()
    title_families: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    min_fit_score: float | None = None
    max_fit_score: float | None = None
    min_preference_score: float | None = None
    max_preference_score: float | None = None
    min_confidence_score: float | None = None
    max_confidence_score: float | None = None
    min_priority_score: float | None = None
    max_priority_score: float | None = None
    posted_from: date | str | None = None
    posted_to: date | str | None = None
    sort_by: str = "recommended"

    @property
    def normalized_page(self) -> int:
        return max(1, self.page)

    @property
    def normalized_page_size(self) -> int:
        return max(1, min(self.page_size, 200))


@dataclass(frozen=True)
class FeedPage:
    rows: tuple[FeedProjectionRecord, ...]
    total: int
    page: int
    page_size: int


def _values(values: tuple[str, ...] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    candidates = (values,) if isinstance(values, str) else values
    return tuple(dict.fromkeys(
        value.strip() for value in candidates
        if isinstance(value, str) and value.strip()
    ))


def _apply_multi_select(
    query: Query,
    column,
    selected_values: tuple[str, ...] | str | None,
    *,
    nullable_unknown=None,
    case_insensitive: bool = True,
    unknown_aliases: tuple[str, ...] = (),
    unknown_maps_to_unspecified: bool = True,
    unknown_matches_empty: bool = False,
) -> Query:
    values = list(dict.fromkeys(value.casefold() for value in _values(selected_values)))
    unknown_selected = UNKNOWN_FILTER_VALUE in values
    values = [value for value in values if value != UNKNOWN_FILTER_VALUE]
    for alias in unknown_aliases:
        normalized_alias = alias.casefold()
        if normalized_alias in values:
            values = [value for value in values if value != normalized_alias]
            unknown_selected = True

    clauses = []
    if unknown_selected and nullable_unknown is None and unknown_maps_to_unspecified:
        # Non-null normalized fields encode missing extraction as "unspecified".
        if "unspecified" not in values:
            values.append("unspecified")
    elif unknown_selected and nullable_unknown is None:
        values.append(UNKNOWN_FILTER_VALUE)
    if (
        unknown_selected
        and unknown_matches_empty
        and unknown_maps_to_unspecified
        and UNKNOWN_FILTER_VALUE not in values
    ):
        values.append(UNKNOWN_FILTER_VALUE)
    if values:
        clauses.append(
            func.lower(func.trim(column)).in_(values) if case_insensitive else column.in_(values)
        )
    if unknown_selected and nullable_unknown is not None:
        clauses.append(nullable_unknown)
    if unknown_selected and unknown_matches_empty:
        clauses.append(or_(column.is_(None), func.trim(column) == ""))

    if clauses:
        query = query.filter(or_(*clauses))
    return query


def _date_bound(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    candidate = value.strip()
    if not candidate:
        return None
    return date.fromisoformat(candidate).isoformat()


def build_feed_query(session: Session, spec: FeedQuerySpec) -> Query:
    """Build the unpaginated SQL-native feed projection query.

    Search uses PostgreSQL ``websearch_to_tsquery`` so phrase and negative-term
    syntax remains database-side and GIN-indexable in production.  Tests that
    execute against SQLite simply avoid the search branch; PostgreSQL
    integration tests exercise it at Alembic head.
    """

    query = session.query(FeedProjectionRecord).filter(
        FeedProjectionRecord.truth_pack_hash == spec.truth_pack_hash
    )

    if not spec.include_hidden:
        query = query.filter(FeedProjectionRecord.visible.is_(True))
    tracks = spec.track_values or ((spec.track,) if spec.track else ())
    query = _apply_multi_select(
        query, FeedProjectionRecord.track, tracks,
        case_insensitive=False,
        unknown_matches_empty=True,
    )
    decisions = spec.decision_values or ((spec.decision,) if spec.decision else ())
    if decisions:
        query = _apply_multi_select(
            query, FeedProjectionRecord.qualification_decision, decisions,
            case_insensitive=True,
            unknown_matches_empty=True,
        )
    if not any(value.strip().casefold() == "ineligible" for value in decisions):
        # Only a proven ineligible decision is excluded. A missing or review-
        # required decision remains available for review.
        query = query.filter(or_(
            FeedProjectionRecord.qualification_decision.is_(None),
            func.lower(FeedProjectionRecord.qualification_decision) != "ineligible",
        ))
    if spec.feedback_labels:
        query = query.filter(exists().where(
            FounderFeedbackRecord.opportunity_id == FeedProjectionRecord.opportunity_id,
            func.lower(FounderFeedbackRecord.feedback_label).in_([value.casefold() for value in spec.feedback_labels]),
        ))
    if spec.activity_types:
        query = query.filter(exists().where(
            FounderActivityEventRecord.opportunity_id == FeedProjectionRecord.opportunity_id,
            func.lower(FounderActivityEventRecord.action_type).in_([value.casefold() for value in spec.activity_types]),
        ))
    if spec.min_score is not None:
        query = query.filter(FeedProjectionRecord.fit_score >= spec.min_score)
    if spec.max_score is not None:
        query = query.filter(FeedProjectionRecord.fit_score <= spec.max_score)
    score_ranges = (
        (FeedProjectionRecord.fit_score, spec.min_fit_score, spec.max_fit_score),
        (FeedProjectionRecord.preference_score, spec.min_preference_score, spec.max_preference_score),
        (FeedProjectionRecord.confidence_score, spec.min_confidence_score, spec.max_confidence_score),
        (FeedProjectionRecord.priority_score, spec.min_priority_score, spec.max_priority_score),
    )
    for column, minimum, maximum in score_ranges:
        if minimum is not None:
            query = query.filter(column >= minimum)
        if maximum is not None:
            query = query.filter(column <= maximum)

    lower_dates = [bound for bound in (spec.since, _date_bound(spec.posted_from)) if bound]
    upper_date = _date_bound(spec.posted_to)
    if lower_dates:
        query = query.filter(FeedProjectionRecord.posted_date >= max(lower_dates))
    if upper_date:
        query = query.filter(FeedProjectionRecord.posted_date <= upper_date)

    work_modes = spec.work_modes or ((spec.work_mode,) if spec.work_mode else ())
    query = _apply_multi_select(
        query, FeedProjectionRecord.work_mode, work_modes,
        case_insensitive=True,
        unknown_matches_empty=True,
    )
    countries = spec.location_countries or ((spec.location_country,) if spec.location_country else ())
    query = _apply_multi_select(
        query, FeedProjectionRecord.location_country, countries,
        nullable_unknown=or_(
            FeedProjectionRecord.location_country.is_(None),
            func.trim(FeedProjectionRecord.location_country) == "",
            func.lower(func.trim(FeedProjectionRecord.location_country)) == UNKNOWN_FILTER_VALUE,
        ),
        case_insensitive=True,
    )
    for column, values in (
        (FeedProjectionRecord.location_city, spec.location_cities),
        (FeedProjectionRecord.target_tier, spec.target_tiers),
    ):
        query = _apply_multi_select(
            query, column, values,
            nullable_unknown=or_(
                column.is_(None),
                func.trim(column) == "",
                func.lower(func.trim(column)) == UNKNOWN_FILTER_VALUE,
            ),
            case_insensitive=True,
        )
    query = _apply_multi_select(
        query, FeedProjectionRecord.remote_scope, spec.remote_scopes,
        case_insensitive=True,
        unknown_matches_empty=True,
    )
    query = _apply_multi_select(
        query, FeedProjectionRecord.employment_type, spec.employment_types,
        case_insensitive=True,
        unknown_matches_empty=True,
    )
    query = _apply_multi_select(
        query, FeedProjectionRecord.seniority_level, spec.seniority_levels,
        case_insensitive=True,
        unknown_matches_empty=True,
    )
    families = spec.title_families or ((spec.title_family,) if spec.title_family else ())
    query = _apply_multi_select(
        query, FeedProjectionRecord.title_family, families,
        nullable_unknown=or_(
            FeedProjectionRecord.title_family.is_(None),
            func.lower(func.trim(FeedProjectionRecord.title_family)).in_(("", "other", "unknown")),
        ),
        case_insensitive=True,
        unknown_aliases=("other",),
    )
    sources = spec.source_ids or ((spec.source_id,) if spec.source_id else ())
    query = _apply_multi_select(
        query, FeedProjectionRecord.source_id, sources,
        case_insensitive=True,
        unknown_maps_to_unspecified=False,
        unknown_matches_empty=True,
    )
    if spec.q and spec.q.strip():
        tsquery = func.websearch_to_tsquery(literal_column("'simple'"), spec.q.strip())
        query = query.filter(FeedProjectionRecord.search_tsv.op("@@")(tsquery))

    if not spec.include_tracked:
        as_of = spec.as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is not None:
            as_of = as_of.astimezone(timezone.utc).replace(tzinfo=None)
        active_triage = exists().where(
            FounderTriageStateRecord.opportunity_id == FeedProjectionRecord.opportunity_id,
            or_(
                FounderTriageStateRecord.state != "snoozed",
                FounderTriageStateRecord.snoozed_until.is_(None),
                FounderTriageStateRecord.snoozed_until > as_of,
            ),
        )
        submitted_action = exists().where(
            OutboundActionRecordModel.opportunity_id == FeedProjectionRecord.opportunity_id,
            OutboundActionRecordModel.action_status == ActionStatus.SUBMITTED.value,
        )
        query = query.filter(not_(active_triage), not_(submitted_action))

    return query


def ordered_feed_query(query: Query, sort_by: str = "recommended") -> Query:
    """Apply a supported deterministic founder-feed order entirely in SQL."""
    if sort_by not in FEED_SORTS:
        raise ValueError(f"unsupported feed sort: {sort_by!r}")

    if sort_by == "fit_desc":
        ordering = (FeedProjectionRecord.fit_score.desc().nullslast(),)
    elif sort_by == "fit_asc":
        ordering = (FeedProjectionRecord.fit_score.asc().nullslast(),)
    elif sort_by == "newest_posted":
        ordering = (FeedProjectionRecord.posted_date.desc().nullslast(),)
    elif sort_by == "oldest_posted":
        ordering = (FeedProjectionRecord.posted_date.asc().nullslast(),)
    elif sort_by == "remote_first":
        ordering = (
            case((func.lower(FeedProjectionRecord.work_mode) == "remote", 0), else_=1).asc(),
            FeedProjectionRecord.priority_score.desc().nullslast(),
        )
    else:
        ordering = (FeedProjectionRecord.priority_score.desc().nullslast(),)
    return query.order_by(*ordering, FeedProjectionRecord.id.asc())


def feed_page(session: Session, spec: FeedQuerySpec) -> FeedPage:
    """Return one bounded page without hydrating the rest of the corpus."""

    base = build_feed_query(session, spec)
    total = base.order_by(None).count()
    page = spec.normalized_page
    page_size = spec.normalized_page_size
    rows: Iterable[FeedProjectionRecord] = (
        ordered_feed_query(base, spec.sort_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return FeedPage(
        rows=tuple(rows),
        total=total,
        page=page,
        page_size=page_size,
    )
