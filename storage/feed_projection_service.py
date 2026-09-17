from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from api.facets import FacetSettingsRow, apply_facets
from api.filters import (
    FILTER_DEFINITIONS_BY_ID,
    FilterSettingsRow,
    OpportunityFilterContext,
    _safe_float,
    apply_filters,
)
from api.serialization import unpack_dimension_scores, unpack_evaluation_detail, unpack_reasons
from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.models import (
    FieldProvenanceRecord,
    FounderFacetRecord,
    FounderFilterSettingRecord,
    MatchEvaluationRecord,
    OpportunityRecord,
)

PROJECTION_VERSION = "v1"
_COMPENSATION_FIELDS = (
    "compensation.min_amount",
    "compensation.max_amount",
    "compensation.currency",
)


@dataclass(frozen=True)
class ProjectionRebuildStats:
    inserted: int = 0
    updated: int = 0
    skipped_without_evaluation: int = 0
    batches: int = 0
    last_opportunity_id: str | None = None

    @property
    def projected(self) -> int:
        return self.inserted + self.updated


def load_filter_settings(session: Session) -> dict[str, FilterSettingsRow]:
    settings: dict[str, FilterSettingsRow] = {}
    for row in session.query(FounderFilterSettingRecord).all():
        try:
            params = json.loads(row.params_json) if row.params_json else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            params = {}
        settings[row.filter_id] = FilterSettingsRow(
            enabled=bool(row.enabled),
            mode=row.mode,
            params=params,
        )
    return settings


def load_facet_settings(session: Session) -> dict[str, FacetSettingsRow]:
    settings: dict[str, FacetSettingsRow] = {}
    for row in session.query(FounderFacetRecord).all():
        try:
            payload = json.loads(row.values_json) if row.values_json else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        settings[row.facet_id] = FacetSettingsRow(
            include=tuple(payload.get("include") or []),
            exclude=tuple(payload.get("exclude") or []),
        )
    return settings


def _contexts_for_truth_pack(
    session: Session,
    truth_graph: Any,
    truth_pack_hash: str,
    opportunities: list[OpportunityRecord],
) -> dict[str, tuple[OpportunityFilterContext, MatchEvaluationRecord]]:
    if not opportunities:
        return {}

    ids = [opp.id for opp in opportunities]
    evaluations = (
        session.query(MatchEvaluationRecord)
        .filter(
            MatchEvaluationRecord.opportunity_id.in_(ids),
            MatchEvaluationRecord.truth_pack_hash == truth_pack_hash,
        )
        .all()
    )
    evaluation_by_id = {row.opportunity_id: row for row in evaluations}

    compensation: dict[str, dict[str, Any]] = {}
    for row in (
        session.query(FieldProvenanceRecord)
        .filter(
            FieldProvenanceRecord.opportunity_id.in_(ids),
            FieldProvenanceRecord.field_name.in_(_COMPENSATION_FIELDS),
        )
        .all()
    ):
        compensation.setdefault(row.opportunity_id, {})[row.field_name] = row.normalized_value

    result: dict[str, tuple[OpportunityFilterContext, MatchEvaluationRecord]] = {}
    for opp in opportunities:
        evaluation = evaluation_by_id.get(opp.id)
        if evaluation is None:
            continue
        comp = compensation.get(opp.id, {})
        context = OpportunityFilterContext(
            opp=opp,
            decision=evaluation.qualification_decision,
            fit_score=evaluation.fit_score,
            reasons=unpack_reasons(evaluation.reasons_json),
            evaluation_detail=unpack_evaluation_detail(evaluation.evaluation_detail_json),
            dimension_scores=unpack_dimension_scores(evaluation.dimension_scores_json),
            compensation_min=_safe_float(comp.get("compensation.min_amount")),
            compensation_max=_safe_float(comp.get("compensation.max_amount")),
            compensation_currency=comp.get("compensation.currency"),
            truth_graph=truth_graph,
        )
        result[opp.id] = (context, evaluation)
    return result


def _search_text(opp: OpportunityRecord) -> str:
    parts = (
        opp.title,
        opp.organization,
        opp.description,
        opp.location_city,
        opp.location_region,
        opp.location_country,
        opp.source_id,
        opp.track,
        opp.title_family,
    )
    return " ".join(str(part).strip() for part in parts if part and str(part).strip())


def _opportunity_type(opp: OpportunityRecord) -> str | None:
    if not opp.raw_payload_json:
        return None
    try:
        payload = json.loads(opp.raw_payload_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("opportunity_type", "type"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:32]
    return None


def _specific_filter_match(filter_id: str, ctx: OpportunityFilterContext) -> bool:
    definition = FILTER_DEFINITIONS_BY_ID[filter_id]
    try:
        return bool(definition.matcher(ctx, definition.default_params))
    except (TypeError, ValueError, AttributeError):
        return False


def build_projection_record(
    opportunity: OpportunityRecord,
    context: OpportunityFilterContext,
    evaluation: MatchEvaluationRecord,
    *,
    truth_pack_hash: str,
    filter_settings: dict[str, FilterSettingsRow],
    facet_settings: dict[str, FacetSettingsRow],
    projected_at: datetime | None = None,
) -> FeedProjectionRecord:
    if evaluation.truth_pack_hash != truth_pack_hash:
        raise ValueError("evaluation truth pack does not match projection truth pack")
    if evaluation.opportunity_id != opportunity.id:
        raise ValueError("evaluation opportunity does not match projection opportunity")

    filter_outcome = apply_filters(context, filter_settings)
    facet_outcome = apply_facets(context, facet_settings)
    hidden_by = list(filter_outcome.hidden_by) + [
        f"facet:{facet_id}" for facet_id in facet_outcome.hidden_by
    ]
    fit_score = float(evaluation.fit_score)
    # Existing request ordering is rank-penalty tier first, then fit score. Fit
    # is constrained to 0..100, so a 1000-point tier gap preserves that order
    # without mutating the persisted fit score itself.
    priority_score = fit_score - (1000.0 * filter_outcome.rank_penalty)
    now = projected_at or datetime.now(timezone.utc)

    return FeedProjectionRecord(
        id=projection_identity(opportunity.id, truth_pack_hash),
        opportunity_id=opportunity.id,
        opportunity_content_hash=opportunity.content_hash,
        truth_pack_hash=truth_pack_hash,
        projection_version=PROJECTION_VERSION,
        title=opportunity.title,
        organization=opportunity.organization,
        source_id=opportunity.source_id,
        source_url=opportunity.source_url,
        posted_date=opportunity.posted_date,
        track=opportunity.track,
        opportunity_type=_opportunity_type(opportunity),
        title_family=opportunity.title_family,
        seniority_level=opportunity.seniority_level,
        work_mode=opportunity.work_mode,
        location_country=opportunity.location_country,
        location_city=opportunity.location_city,
        location_region=opportunity.location_region,
        remote_scope=opportunity.remote_scope,
        remote_scope_regions=opportunity.remote_scope_regions,
        employment_type=opportunity.employment_type,
        qualification_decision=evaluation.qualification_decision,
        fit_score=fit_score,
        priority_score=priority_score,
        reasons_json=evaluation.reasons_json,
        red_line_match=_specific_filter_match("red_lines", context),
        excluded_industry_match=_specific_filter_match("excluded_industries", context),
        visible=not hidden_by,
        visibility_reason=json.dumps(hidden_by, separators=(",", ":")) if hidden_by else None,
        search_text=_search_text(opportunity),
        search_tsv=None,
        evaluated_at=evaluation.evaluated_at,
        projected_at=now,
    )


def upsert_projection(session: Session, record: FeedProjectionRecord) -> bool:
    existing = session.get(FeedProjectionRecord, record.id)
    inserted = existing is None
    managed = session.merge(record)
    session.flush()

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text(
                "UPDATE feed_projection "
                "SET search_tsv = to_tsvector('simple', search_text) "
                "WHERE id = :projection_id"
            ),
            {"projection_id": managed.id},
        )
    return inserted


def rebuild_feed_projection(
    session: Session,
    *,
    truth_graph: Any,
    truth_pack_hash: str,
    filter_settings: dict[str, FilterSettingsRow] | None = None,
    facet_settings: dict[str, FacetSettingsRow] | None = None,
    batch_size: int = 500,
    start_after: str | None = None,
    commit_each_batch: bool = False,
) -> ProjectionRebuildStats:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    filters = filter_settings if filter_settings is not None else load_filter_settings(session)
    facets = facet_settings if facet_settings is not None else load_facet_settings(session)
    inserted = updated = skipped = batches = 0
    cursor = start_after

    while True:
        query = (
            session.query(OpportunityRecord)
            .join(
                MatchEvaluationRecord,
                and_(
                    MatchEvaluationRecord.opportunity_id == OpportunityRecord.id,
                    MatchEvaluationRecord.truth_pack_hash == truth_pack_hash,
                ),
            )
            .order_by(OpportunityRecord.id.asc())
        )
        if cursor is not None:
            query = query.filter(OpportunityRecord.id > cursor)
        opportunities = query.limit(batch_size).all()
        if not opportunities:
            break

        contexts = _contexts_for_truth_pack(
            session, truth_graph, truth_pack_hash, opportunities
        )
        projected_at = datetime.now(timezone.utc)
        for opportunity in opportunities:
            pair = contexts.get(opportunity.id)
            if pair is None:
                skipped += 1
                continue
            context, evaluation = pair
            record = build_projection_record(
                opportunity,
                context,
                evaluation,
                truth_pack_hash=truth_pack_hash,
                filter_settings=filters,
                facet_settings=facets,
                projected_at=projected_at,
            )
            if upsert_projection(session, record):
                inserted += 1
            else:
                updated += 1

        cursor = opportunities[-1].id
        batches += 1
        if commit_each_batch:
            session.commit()

    return ProjectionRebuildStats(
        inserted=inserted,
        updated=updated,
        skipped_without_evaluation=skipped,
        batches=batches,
        last_opportunity_id=cursor,
    )
