from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func, literal_column
from sqlalchemy.orm import Query, Session

from storage.feed_projection import FeedProjectionRecord


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
    min_score: float | None = None
    max_score: float | None = None
    since: str | None = None
    work_mode: str | None = None
    location_country: str | None = None
    title_family: str | None = None
    source_id: str | None = None
    q: str | None = None
    include_hidden: bool = False
    page: int = 1
    page_size: int = 25

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
    if spec.track:
        query = query.filter(FeedProjectionRecord.track == spec.track)
    if spec.decision:
        query = query.filter(
            FeedProjectionRecord.qualification_decision == spec.decision
        )
    if spec.min_score is not None:
        query = query.filter(FeedProjectionRecord.fit_score >= spec.min_score)
    if spec.max_score is not None:
        query = query.filter(FeedProjectionRecord.fit_score <= spec.max_score)
    if spec.since:
        query = query.filter(FeedProjectionRecord.posted_date >= spec.since)
    if spec.work_mode:
        query = query.filter(FeedProjectionRecord.work_mode == spec.work_mode)
    if spec.location_country:
        query = query.filter(
            FeedProjectionRecord.location_country == spec.location_country
        )
    if spec.title_family:
        query = query.filter(FeedProjectionRecord.title_family == spec.title_family)
    if spec.source_id:
        query = query.filter(FeedProjectionRecord.source_id == spec.source_id)
    if spec.q and spec.q.strip():
        tsquery = func.websearch_to_tsquery(literal_column("'simple'"), spec.q.strip())
        query = query.filter(FeedProjectionRecord.search_tsv.op("@@")(tsquery))

    return query


def ordered_feed_query(query: Query) -> Query:
    """Apply deterministic founder-feed ordering entirely in SQL."""

    return query.order_by(
        FeedProjectionRecord.priority_score.desc(),
        FeedProjectionRecord.fit_score.desc(),
        FeedProjectionRecord.posted_date.desc().nullslast(),
        FeedProjectionRecord.id.asc(),
    )


def feed_page(session: Session, spec: FeedQuerySpec) -> FeedPage:
    """Return one bounded page without hydrating the rest of the corpus."""

    base = build_feed_query(session, spec)
    total = base.order_by(None).count()
    page = spec.normalized_page
    page_size = spec.normalized_page_size
    rows: Iterable[FeedProjectionRecord] = (
        ordered_feed_query(base)
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
