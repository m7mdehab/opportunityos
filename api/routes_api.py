"""Every non-auth route. Gated globally by `require_session` at the
APIRouter level so a new route added here cannot ship unguarded."""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, defer

from core.logging import get_logger
from feedback.models import FeedbackLabel
from feedback.service import FounderFeedbackService
from matching.artifact_validation import validate_artifact_claims
from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from matching.templates import TEMPLATES
from matching.title_family import normalize_title
from opportunity.manual_sources import MANUAL_SOURCES, tutoring_platform_cards
from opportunity.models import Opportunity, Track
from opportunity.registry import SourceRegistry
from truth.models import CareerProfile
from outbound.models import ActionStatus, ExecutionMode
from storage.models import (
    FieldProvenanceRecord,
    FounderFacetRecord,
    FounderFeedbackRecord,
    FounderFilterSettingRecord,
    FounderOpportunityViewRecord,
    FounderSavedViewRecord,
    FounderTriageStateRecord,
    MatchEvaluationRecord,
    OpportunityFamilyRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
    SourcePollRunRecord,
)
from storage.repository import StorageRepository
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack
from truth.validator import ClaimValidator
from worker.queue import BackgroundWorkerQueue

from . import artifact_cache
from .deps import get_db, get_repository, require_session
from .facets import (
    FACET_DEFINITIONS_BY_ID,
    FacetSettingsRow,
    apply_facets,
    facet_payload,
    hidden_reasons_audit,
    poll_hide_fraction_warnings,
    unhide_by_reason,
)
from .filters import (
    FILTER_DEFINITIONS,
    FILTER_DEFINITIONS_BY_ID,
    FILTER_MODES,
    FilterSettingsRow,
    OpportunityFilterContext,
    ParamValidationError,
    affected_count as filter_affected_count,
    apply_filters,
    build_filter_contexts,
    _excluded_industries_matches,
    _founder_target_role_families,
    _founder_track_preference,
    _red_lines_matches,
    _safe_float,
    to_naive_utc,
    unavailable_reason,
    validate_filter_params,
)
from .saved_views import (
    create_saved_view,
    delete_saved_view,
    list_saved_views,
    update_saved_view,
)
from .search import is_query_unparseable, rank_key, search_opportunity_ids
from .serialization import (
    serialize_constraint,
    serialize_dimension_score,
    serialize_opportunity_extraction_fields,
    strengths_gaps_unknowns_from_reasons,
    top_reasons_from_list,
    unpack_dimension_scores,
    unpack_evaluation_detail,
    unpack_reasons,
)

logger = get_logger("api.routes")

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"

# OpportunityRecord includes full descriptions and raw source payloads.  A
# production feed has tens of thousands of rows, so requests must process the
# corpus in bounded chunks instead of materialising every ORM row at once.
_OPPORTUNITY_BATCH_SIZE = 5000


def _opportunity_batches(query, batch_size: int | None = None) -> Iterator[list[OpportunityRecord]]:
    batch_size = batch_size or _OPPORTUNITY_BATCH_SIZE
    offset = 0
    ordered = query.order_by(OpportunityRecord.id.asc())
    while True:
        batch = ordered.offset(offset).limit(batch_size).all()
        if not batch:
            return
        yield batch
        offset += len(batch)


def _opportunity_query(session: Session):
    # Source payloads can dwarf every field used by filtering and cards.  Keep
    # them deferred so broad-feed reads do not transfer/retain irrelevant JSON.
    return session.query(OpportunityRecord).options(defer(OpportunityRecord.raw_payload_json))


def _ranking_filter_contexts(
    session: Session,
    truth_graph: Any,
    opportunities: list[OpportunityRecord],
    filter_settings: dict[str, FilterSettingsRow],
    facet_settings: dict[str, FacetSettingsRow],
) -> list[OpportunityFilterContext]:
    """Build only the context fields that can change visibility or rank.

    Card-only reasons and label-only constraint details are hydrated after
    pagination for the at-most-200 returned rows.  If the compensation filter
    is enabled, use the full builder because its legacy values come from field
    provenance rather than OpportunityRecord columns.
    """
    def affects_order(filter_id: str) -> bool:
        row = filter_settings.get(filter_id)
        definition = FILTER_DEFINITIONS_BY_ID[filter_id]
        enabled = row.enabled if row is not None else definition.default_enabled
        mode = row.mode if row is not None else definition.default_mode
        return enabled and mode in {"hide", "rank_only"}

    compensation = filter_settings.get("compensation_floor")
    compensation_facet = facet_settings.get("compensation_stated")
    if (
        (compensation.enabled if compensation is not None else FILTER_DEFINITIONS_BY_ID["compensation_floor"].default_enabled)
        or (compensation_facet is not None and bool(compensation_facet.include or compensation_facet.exclude))
    ):
        return build_filter_contexts(session, truth_graph, opportunities)
    if not opportunities:
        return []

    detail_needed = any(affects_order(filter_id) for filter_id in ("geo_eligibility", "work_mode_onsite"))
    dimensions_needed = affects_order("premium_fulltime_onsite")
    opp_ids = [opp.id for opp in opportunities]
    evaluations = (
        session.query(MatchEvaluationRecord)
        .filter(MatchEvaluationRecord.opportunity_id.in_(opp_ids))
        .order_by(MatchEvaluationRecord.evaluated_at.desc(), MatchEvaluationRecord.created_at.desc())
        .all()
    )
    latest: dict[str, MatchEvaluationRecord] = {}
    for evaluation in evaluations:
        latest.setdefault(evaluation.opportunity_id, evaluation)

    contexts: list[OpportunityFilterContext] = []
    for opp in opportunities:
        evaluation = latest.get(opp.id)
        contexts.append(
            OpportunityFilterContext(
                opp=opp,
                decision=evaluation.qualification_decision if evaluation else None,
                fit_score=evaluation.fit_score if evaluation else None,
                reasons=[],
                evaluation_detail=(
                    unpack_evaluation_detail(evaluation.evaluation_detail_json)
                    if evaluation is not None and detail_needed
                    else unpack_evaluation_detail(None)
                ),
                dimension_scores=(
                    unpack_dimension_scores(evaluation.dimension_scores_json)
                    if evaluation is not None and dimensions_needed
                    else []
                ),
                compensation_min=None,
                compensation_max=None,
                compensation_currency=None,
                truth_graph=truth_graph,
            )
        )
    return contexts


def _filter_enabled_mode(
    filter_id: str,
    settings: dict[str, FilterSettingsRow],
) -> tuple[bool, str]:
    row = settings.get(filter_id)
    definition = FILTER_DEFINITIONS_BY_ID[filter_id]
    return (
        row.enabled if row is not None else definition.default_enabled,
        row.mode if row is not None else definition.default_mode,
    )


def _can_lightweight_prefilter_hidden(
    filter_settings: dict[str, FilterSettingsRow],
    facet_settings: dict[str, FacetSettingsRow],
) -> bool:
    if any(row.include or row.exclude for row in facet_settings.values()):
        return False
    allowed = {"red_lines", "excluded_industries"}
    for definition in FILTER_DEFINITIONS:
        enabled, mode = _filter_enabled_mode(definition.filter_id, filter_settings)
        if enabled and mode == "hide" and definition.filter_id not in allowed:
            return False
    return True


def _can_lightweight_rank(filter_settings: dict[str, FilterSettingsRow]) -> bool:
    compensation_enabled, _ = _filter_enabled_mode("compensation_floor", filter_settings)
    if compensation_enabled:
        return False
    supported_rank_filters = {"track_preference", "target_roles", "premium_fulltime_onsite"}
    for definition in FILTER_DEFINITIONS:
        enabled, mode = _filter_enabled_mode(definition.filter_id, filter_settings)
        if enabled and mode == "rank_only" and definition.filter_id not in supported_rank_filters:
            return False
    return True


_LIGHTWEIGHT_HIDDEN_CACHE_MAX_ENTRIES = 100_000
_LIGHTWEIGHT_HIDDEN_CACHE: dict[tuple[Any, bool, bool, str, str], bool] = {}


def _lightweight_hidden_ids(query, truth_graph: Any, filter_settings: dict[str, FilterSettingsRow]) -> set[str]:
    """Return exact hidden IDs without hydrating full ORM/evaluation rows."""
    red_lines_active = _filter_enabled_mode("red_lines", filter_settings) == (True, "hide")
    industries_active = _filter_enabled_mode("excluded_industries", filter_settings) == (True, "hide")
    if truth_graph is None or not (red_lines_active or industries_active):
        return set()

    if len(_LIGHTWEIGHT_HIDDEN_CACHE) > _LIGHTWEIGHT_HIDDEN_CACHE_MAX_ENTRIES:
        _LIGHTWEIGHT_HIDDEN_CACHE.clear()

    references = query.with_entities(OpportunityRecord.id, OpportunityRecord.content_hash).all()
    reference_keys = [
        (truth_graph, red_lines_active, industries_active, reference.id, reference.content_hash)
        for reference in references
    ]
    missing_ids = [
        reference.id
        for reference, cache_key in zip(references, reference_keys)
        if cache_key not in _LIGHTWEIGHT_HIDDEN_CACHE
    ]
    if not missing_ids:
        return {
            reference.id
            for reference, cache_key in zip(references, reference_keys)
            if _LIGHTWEIGHT_HIDDEN_CACHE[cache_key]
        }

    candidates = query.with_entities(
        OpportunityRecord.id,
        OpportunityRecord.title,
        OpportunityRecord.organization,
        OpportunityRecord.description,
        OpportunityRecord.content_hash,
    )
    if len(missing_ids) != len(references):
        candidates = candidates.filter(OpportunityRecord.id.in_(missing_ids))

    def is_hidden(source) -> bool:
        opp = SimpleNamespace(
            id=source.id,
            title=source.title,
            organization=source.organization,
            description=source.description,
            content_hash=source.content_hash,
        )
        ctx = OpportunityFilterContext(
            opp=opp,
            decision=None,
            fit_score=None,
            reasons=[],
            evaluation_detail={},
            dimension_scores=[],
            compensation_min=None,
            compensation_max=None,
            compensation_currency=None,
            truth_graph=truth_graph,
        )
        return (
            (red_lines_active and _red_lines_matches(ctx, {}))
            or (industries_active and _excluded_industries_matches(ctx, {}))
        )

    source_rows = candidates.all()
    if len(source_rows) < 1000:
        hidden = list(map(is_hidden, source_rows))
    else:
        # The matchers spend almost all their time in independent C-level
        # substring/regex scans over large descriptions. A small bounded pool
        # keeps a cold production feed inside the reverse-proxy request window.
        with ThreadPoolExecutor(max_workers=4) as executor:
            hidden = list(executor.map(is_hidden, source_rows, chunksize=64))
    for source, matched in zip(source_rows, hidden):
        cache_key = (truth_graph, red_lines_active, industries_active, source.id, source.content_hash)
        _LIGHTWEIGHT_HIDDEN_CACHE[cache_key] = matched
    return {
        reference.id
        for reference, cache_key in zip(references, reference_keys)
        if _LIGHTWEIGHT_HIDDEN_CACHE.get(cache_key, False)
    }


def _lightweight_rank_penalty(
    *,
    track: str,
    title: str,
    title_family: str | None,
    dimension_scores_json: str | None,
    truth_graph: Any,
    filter_settings: dict[str, FilterSettingsRow],
) -> int:
    penalty = 0
    if _filter_enabled_mode("track_preference", filter_settings) == (True, "rank_only"):
        preferred = _founder_track_preference(truth_graph)
        if preferred is not None and track.casefold() != preferred:
            penalty += 1
    if _filter_enabled_mode("target_roles", filter_settings) == (True, "rank_only"):
        target_families = _founder_target_role_families(truth_graph)
        family = title_family or normalize_title(title)[0]
        if target_families and family not in target_families:
            penalty += 1
    if _filter_enabled_mode("premium_fulltime_onsite", filter_settings) == (True, "rank_only"):
        # The stable tag is a necessary condition; avoid decoding tens of
        # thousands of JSON arrays that cannot possibly contain it.
        if dimension_scores_json and "premium_shortfall" in dimension_scores_json:
            dimensions = unpack_dimension_scores(dimension_scores_json)
            if any(
                dim.get("dimension_name") == "compensation_fit"
                and "premium_shortfall" in (dim.get("signal_tags") or [])
                for dim in dimensions
            ):
                penalty += 1
    return penalty


def _merge_facet_payloads(aggregate: list[dict[str, Any]], partial: list[dict[str, Any]]) -> None:
    for target, source in zip(aggregate, partial):
        target["excluded_count"] += source["excluded_count"]
        counts = {item["value"]: item["count"] for item in target["values"]}
        states = {item["value"]: item["state"] for item in target["values"]}
        for item in source["values"]:
            counts[item["value"]] = counts.get(item["value"], 0) + item["count"]
            states[item["value"]] = item["state"]
        target["values"] = [
            {"value": value, "count": count, "state": states[value]}
            for value, count in sorted(counts.items())
        ]


# --------------------------------------------------------------------------
# Timezone convention
#
# Every `DateTime` column in `storage/migrations` (0001 and 0002) is naive
# (`sa.DateTime()`, no `timezone=True`) -- but every value this codebase
# writes into one is `datetime.now(timezone.utc)`. So a value read back
# through the ORM is naive but always represents a UTC instant; comparing it
# directly against an aware `datetime.now(timezone.utc)` raises
# `TypeError: can't compare offset-naive and offset-aware datetimes`
# (council-flagged: this was a real, reachable crash in snooze-expiry
# handling). `_as_aware_utc` is the single place that convention is made
# explicit: every DB-read datetime passes through it before either being
# compared against an aware value or serialised via `_iso`, so this module
# never mixes naive and aware datetimes. SQLAlchemy `.filter(...)` query
# expressions (e.g. the dashboard's day-bucket filters) are unaffected --
# those comparisons happen server-side in SQL, not between two Python
# `datetime` objects, so they carry no such hazard.
# --------------------------------------------------------------------------

def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    aware = _as_aware_utc(value)
    return aware.isoformat() if aware is not None else None


# --------------------------------------------------------------------------
# Opportunities: list and detail
# --------------------------------------------------------------------------

def _latest_evaluation(session: Session, opportunity_id: str) -> MatchEvaluationRecord | None:
    return (
        session.query(MatchEvaluationRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(MatchEvaluationRecord.evaluated_at.desc(), MatchEvaluationRecord.created_at.desc())
        .first()
    )


def _batch_action_states(session: Session, opportunity_ids: list[str]) -> dict[str, str]:
    if not opportunity_ids:
        return {}
    results: dict[str, str] = {}
    triages = (
        session.query(FounderTriageStateRecord)
        .filter(FounderTriageStateRecord.opportunity_id.in_(opportunity_ids))
        .all()
    )
    now = datetime.now(timezone.utc)
    needs_submitted = set(opportunity_ids)
    for triage in triages:
        if triage.state == "snoozed":
            snoozed_until = _as_aware_utc(triage.snoozed_until)
            snooze_still_active = snoozed_until is None or snoozed_until > now
            if snooze_still_active:
                results[triage.opportunity_id] = "snoozed"
                needs_submitted.discard(triage.opportunity_id)
        else:
            results[triage.opportunity_id] = triage.state
            needs_submitted.discard(triage.opportunity_id)

    if needs_submitted:
        submitted_opp_ids = {
            row[0]
            for row in session.query(OutboundActionRecordModel.opportunity_id)
            .filter(
                OutboundActionRecordModel.opportunity_id.in_(needs_submitted),
                OutboundActionRecordModel.action_status == ActionStatus.SUBMITTED.value,
            )
            .all()
        }
        for opp_id in submitted_opp_ids:
            results[opp_id] = "submitted"

    return results


def _batch_feedback_labels(session: Session, opportunity_ids: list[str]) -> dict[str, str]:
    if not opportunity_ids:
        return {}
    fbs = (
        session.query(FounderFeedbackRecord)
        .filter(FounderFeedbackRecord.opportunity_id.in_(opportunity_ids))
        .order_by(FounderFeedbackRecord.created_at.asc())
        .all()
    )
    return {fb.opportunity_id: fb.feedback_label for fb in fbs if fb.feedback_label}


def _latest_action_state(session: Session, opportunity_id: str) -> str | None:
    return _batch_action_states(session, [opportunity_id]).get(opportunity_id)


def _latest_feedback_label(session: Session, opportunity_id: str) -> str | None:
    return _batch_feedback_labels(session, [opportunity_id]).get(opportunity_id)



# --------------------------------------------------------------------------
# D3: founder-controlled filters
# --------------------------------------------------------------------------


def _load_filter_settings(session: Session) -> dict[str, FilterSettingsRow]:
    """Every `founder_filter_settings` row, keyed by `filter_id`. A row
    missing entirely (should not happen once migration 0003 has seeded all
    ten -- see `_D3_FILTER_SEED`) is simply absent from this dict;
    `filters.apply_filters` / `filters.affected_count` fall back to that
    filter's `FilterDefinition` defaults in that case."""
    rows = session.query(FounderFilterSettingRecord).all()
    settings: dict[str, FilterSettingsRow] = {}
    for row in rows:
        params = json.loads(row.params_json) if row.params_json else {}
        settings[row.filter_id] = FilterSettingsRow(enabled=row.enabled, mode=row.mode, params=params)
    return settings


def _truth_graph_from_request(request: Request):
    loaded_pack = request.app.state.loaded_truth_pack
    return loaded_pack.graph if loaded_pack is not None else None


_FILTER_AFFECTED_COUNTS_CACHE: dict[tuple[Any, ...], dict[str, int]] = {}


def _filter_affected_counts(session: Session, truth_graph: Any, loaded_pack: Any, settings: dict[str, FilterSettingsRow]):
    opportunity_marker = session.query(
        func.count(OpportunityRecord.id),
        func.max(OpportunityRecord.created_at),
        func.max(OpportunityRecord.reverified_at),
    ).one()
    evaluation_marker = (0, None)
    if loaded_pack is not None:
        evaluation_marker = session.query(
            func.count(MatchEvaluationRecord.id),
            func.max(MatchEvaluationRecord.evaluated_at),
        ).filter(MatchEvaluationRecord.truth_pack_hash == loaded_pack.truth_pack_hash).one()
    settings_marker = tuple(
        sorted(
            (
                filter_id,
                row.enabled,
                row.mode,
                json.dumps(row.params, sort_keys=True, separators=(",", ":")),
            )
            for filter_id, row in settings.items()
        )
    )
    cache_key = (
        loaded_pack.truth_pack_hash if loaded_pack is not None else None,
        tuple(opportunity_marker),
        tuple(evaluation_marker),
        settings_marker,
    )
    cached = _FILTER_AFFECTED_COUNTS_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    affected_counts = {fd.filter_id: 0 for fd in FILTER_DEFINITIONS}
    if loaded_pack is not None:
        rows = (
            session.query(
                OpportunityRecord.id,
                OpportunityRecord.title,
                OpportunityRecord.organization,
                OpportunityRecord.description,
                OpportunityRecord.content_hash,
                OpportunityRecord.track,
                OpportunityRecord.title_family,
                OpportunityRecord.is_stale,
                MatchEvaluationRecord.qualification_decision,
                MatchEvaluationRecord.fit_score,
                MatchEvaluationRecord.evaluation_detail_json,
                MatchEvaluationRecord.dimension_scores_json,
            )
            .outerjoin(
                MatchEvaluationRecord,
                and_(
                    MatchEvaluationRecord.opportunity_id == OpportunityRecord.id,
                    MatchEvaluationRecord.truth_pack_hash == loaded_pack.truth_pack_hash,
                ),
            )
            .all()
        )
        compensation: dict[str, dict[str, Any]] = {}
        for provenance in (
            session.query(
                FieldProvenanceRecord.opportunity_id,
                FieldProvenanceRecord.field_name,
                FieldProvenanceRecord.normalized_value,
            )
            .filter(
                FieldProvenanceRecord.field_name.in_(
                    ("compensation.min_amount", "compensation.max_amount", "compensation.currency")
                )
            )
            .all()
        ):
            compensation.setdefault(provenance.opportunity_id, {})[provenance.field_name] = provenance.normalized_value

        contexts = []
        for row in rows:
            opp = SimpleNamespace(
                id=row.id,
                title=row.title,
                organization=row.organization,
                description=row.description,
                content_hash=row.content_hash,
                track=row.track,
                title_family=row.title_family,
                is_stale=row.is_stale,
            )
            comp = compensation.get(row.id, {})
            contexts.append(
                OpportunityFilterContext(
                    opp=opp,
                    decision=row.qualification_decision,
                    fit_score=row.fit_score,
                    reasons=[],
                    evaluation_detail=(
                        unpack_evaluation_detail(row.evaluation_detail_json)
                        if row.evaluation_detail_json
                        and (
                            "geographic_eligibility" in row.evaluation_detail_json
                            or "work_mode_onsite" in row.evaluation_detail_json
                        )
                        else unpack_evaluation_detail(None)
                    ),
                    dimension_scores=(
                        unpack_dimension_scores(row.dimension_scores_json)
                        if row.dimension_scores_json and "premium_shortfall" in row.dimension_scores_json
                        else []
                    ),
                    compensation_min=_safe_float(comp.get("compensation.min_amount")),
                    compensation_max=_safe_float(comp.get("compensation.max_amount")),
                    compensation_currency=comp.get("compensation.currency"),
                    truth_graph=truth_graph,
                )
            )
        for fd in FILTER_DEFINITIONS:
            row = settings.get(fd.filter_id)
            params = row.params if row is not None else fd.default_params
            affected_counts[fd.filter_id] = filter_affected_count(fd, params, contexts)
    else:
        # A missing pack is a small/degraded-runtime path; preserve the
        # legacy latest-evaluation behavior there.
        for opportunities in _opportunity_batches(_opportunity_query(session)):
            contexts = build_filter_contexts(session, truth_graph, opportunities)
            for fd in FILTER_DEFINITIONS:
                row = settings.get(fd.filter_id)
                params = row.params if row is not None else fd.default_params
                affected_counts[fd.filter_id] += filter_affected_count(fd, params, contexts)
    if len(_FILTER_AFFECTED_COUNTS_CACHE) >= 8:
        _FILTER_AFFECTED_COUNTS_CACHE.clear()
    _FILTER_AFFECTED_COUNTS_CACHE[cache_key] = dict(affected_counts)
    return affected_counts


@router.get("/filters")
def list_filters(request: Request, session: Session = Depends(get_db)):
    settings = _load_filter_settings(session)
    truth_graph = _truth_graph_from_request(request)
    loaded_pack = request.app.state.loaded_truth_pack
    affected_counts = _filter_affected_counts(session, truth_graph, loaded_pack, settings)

    filters_payload = []
    for fd in FILTER_DEFINITIONS:
        row = settings.get(fd.filter_id)
        enabled = row.enabled if row is not None else fd.default_enabled
        mode = row.mode if row is not None else fd.default_mode
        params = row.params if row is not None else dict(fd.default_params)
        filters_payload.append(
            {
                "filter_id": fd.filter_id,
                "enabled": enabled,
                "mode": mode,
                "params": params,
                "affected_count": affected_counts[fd.filter_id],
                "description": fd.description,
                # Council defects 2/3: non-null when this filter has no real
                # data source to evaluate against right now (missing pack
                # assertion, or a pipeline gap upstream) -- see
                # api/filters.py::unavailable_reason.
                "unavailable_reason": unavailable_reason(fd, truth_graph),
            }
        )
    return {"filters": filters_payload}


class FilterUpdateRequest(BaseModel):
    enabled: bool | None = None
    mode: str | None = None
    params: dict[str, Any] | None = None


@router.put("/filters/{filter_id}")
def update_filter(
    filter_id: str,
    payload: FilterUpdateRequest,
    response: Response,
    request: Request,
    session: Session = Depends(get_db),
):
    fd = FILTER_DEFINITIONS_BY_ID.get(filter_id)
    if fd is None:
        raise HTTPException(status_code=404, detail=f"unknown filter_id: {filter_id!r}")

    if payload.mode is not None and payload.mode not in FILTER_MODES:
        response.status_code = 422
        return {"detail": "invalid mode", "allowed": list(FILTER_MODES)}

    # Council defect 1: validate `params` BEFORE any session mutation or
    # commit. A malformed params payload used to be persisted and only fail
    # (500) the moment a later matcher tried to use it -- by which point
    # every GET /api/opportunities and GET /api/filters call was also
    # 500ing, with no way to recover except a raw PUT the drawer itself could
    # no longer even render a form to issue.
    validated_params: dict[str, Any] | None = None
    if payload.params is not None:
        try:
            validated_params = validate_filter_params(filter_id, payload.params)
        except ParamValidationError as error:
            response.status_code = 422
            return {"detail": str(error)}

    now = to_naive_utc(datetime.now(timezone.utc))
    row = session.query(FounderFilterSettingRecord).filter_by(filter_id=filter_id).first()
    if row is None:
        row = FounderFilterSettingRecord(
            filter_id=filter_id,
            enabled=fd.default_enabled,
            mode=fd.default_mode,
            params_json=json.dumps(dict(fd.default_params)),
            updated_at=now,
        )
        session.add(row)

    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.mode is not None:
        row.mode = payload.mode
    if validated_params is not None:
        row.params_json = json.dumps(validated_params)
    row.updated_at = now
    session.commit()

    params = json.loads(row.params_json) if row.params_json else {}
    truth_graph = _truth_graph_from_request(request)
    affected_count = 0
    for opportunities in _opportunity_batches(_opportunity_query(session)):
        contexts = build_filter_contexts(session, truth_graph, opportunities)
        affected_count += filter_affected_count(fd, params, contexts)
    return {
        "filter_id": row.filter_id,
        "enabled": row.enabled,
        "mode": row.mode,
        "params": params,
        "affected_count": affected_count,
        "description": fd.description,
        "unavailable_reason": unavailable_reason(fd, truth_graph),
    }


# --------------------------------------------------------------------------
# C1: generic facets
# --------------------------------------------------------------------------


def _load_facet_settings(session: Session) -> dict[str, FacetSettingsRow]:
    """Every `founder_facets` row, keyed by `facet_id`. A facet with no row
    at all (every facet, on a fresh database -- migration 0004 seeds no
    default facet selections, matching "nothing hides by default except the
    founder's own red lines and excluded industries") is simply absent from
    this dict; `facets.apply_facets` / `facets.facet_hides` treat that as
    `include=() exclude=()` -- the "off" state."""
    rows = session.query(FounderFacetRecord).all()
    settings: dict[str, FacetSettingsRow] = {}
    for row in rows:
        payload = json.loads(row.values_json) if row.values_json else {}
        settings[row.facet_id] = FacetSettingsRow(
            include=tuple(payload.get("include") or []),
            exclude=tuple(payload.get("exclude") or []),
        )
    return settings


def _family_sizes(session: Session, family_keys: list[str | None]) -> dict[str, int]:
    """C5: `OpportunityFamilyRecord.member_count` for every distinct,
    non-null `family_key` among `family_keys`, batched into one query rather
    than one lookup per row (contract: adding fields to the feed item must
    not change how anything is ranked, hidden, or fetched -- N+1 here would
    still be *correct*, just needlessly slow on a real feed page)."""
    keys = {k for k in family_keys if k}
    if not keys:
        return {}
    rows = (
        session.query(OpportunityFamilyRecord.family_key, OpportunityFamilyRecord.member_count)
        .filter(OpportunityFamilyRecord.family_key.in_(keys))
        .all()
    )
    return {family_key: member_count for family_key, member_count in rows if member_count is not None}


@router.get("/facets")
def list_facets(request: Request, session: Session = Depends(get_db)):
    facet_settings = _load_facet_settings(session)
    filter_settings = _load_filter_settings(session)
    truth_graph = _truth_graph_from_request(request)
    loaded_pack = request.app.state.loaded_truth_pack

    # The production defaults only hide the founder's red lines and excluded
    # industries.  In that common case, fetch exactly the scalar fields the
    # facet engine needs and avoid hydrating/unpacking every evaluation's
    # reasons, dimensions, and detail JSON.  The matchers are the same ones
    # used by apply_filters, so visibility and counts remain exact.
    if loaded_pack is not None and _can_lightweight_prefilter_hidden(filter_settings, {}):
        hidden_ids = _lightweight_hidden_ids(_opportunity_query(session), truth_graph, filter_settings)
        rows = (
            session.query(
                OpportunityRecord.id,
                OpportunityRecord.title,
                OpportunityRecord.organization,
                OpportunityRecord.work_mode,
                OpportunityRecord.location_country,
                OpportunityRecord.location_city,
                OpportunityRecord.remote_scope,
                OpportunityRecord.employment_type,
                OpportunityRecord.seniority_level,
                OpportunityRecord.title_family,
                OpportunityRecord.track,
                OpportunityRecord.source_id,
                OpportunityRecord.posted_date,
                MatchEvaluationRecord.qualification_decision,
                MatchEvaluationRecord.fit_score,
            )
            .filter(~OpportunityRecord.id.in_(hidden_ids) if hidden_ids else True)
            .outerjoin(
                MatchEvaluationRecord,
                and_(
                    MatchEvaluationRecord.opportunity_id == OpportunityRecord.id,
                    MatchEvaluationRecord.truth_pack_hash == loaded_pack.truth_pack_hash,
                ),
            )
            .all()
        )
        compensation: dict[str, dict[str, Any]] = {}
        for provenance in (
            session.query(
                FieldProvenanceRecord.opportunity_id,
                FieldProvenanceRecord.field_name,
                FieldProvenanceRecord.normalized_value,
            )
            .filter(
                FieldProvenanceRecord.field_name.in_(
                    ("compensation.min_amount", "compensation.max_amount", "compensation.currency")
                )
            )
            .all()
        ):
            compensation.setdefault(provenance.opportunity_id, {})[provenance.field_name] = provenance.normalized_value

        contexts: list[OpportunityFilterContext] = []
        for row in rows:
            opp = SimpleNamespace(
                id=row.id,
                title=row.title,
                organization=row.organization,
                work_mode=row.work_mode,
                location_country=row.location_country,
                location_city=row.location_city,
                remote_scope=row.remote_scope,
                employment_type=row.employment_type,
                seniority_level=row.seniority_level,
                title_family=row.title_family,
                track=row.track,
                source_id=row.source_id,
                posted_date=row.posted_date,
            )
            comp = compensation.get(row.id, {})
            ctx = OpportunityFilterContext(
                opp=opp,
                decision=row.qualification_decision,
                fit_score=row.fit_score,
                reasons=[],
                evaluation_detail={},
                dimension_scores=[],
                compensation_min=_safe_float(comp.get("compensation.min_amount")),
                compensation_max=_safe_float(comp.get("compensation.max_amount")),
                compensation_currency=comp.get("compensation.currency"),
                truth_graph=truth_graph,
            )
            contexts.append(ctx)
        return {"facets": facet_payload(contexts, facet_settings)}

    aggregate = facet_payload([], facet_settings)
    for opportunities in _opportunity_batches(_opportunity_query(session)):
        contexts = build_filter_contexts(session, truth_graph, opportunities)
        # A facet only ever narrows what the policy filters already show --
        # the same base set GET /api/opportunities uses before facets.
        visible = [ctx for ctx in contexts if not apply_filters(ctx, filter_settings).hidden_by]
        _merge_facet_payloads(aggregate, facet_payload(visible, facet_settings))
    return {"facets": aggregate}


class FacetUpdateRequest(BaseModel):
    include: list[str] | None = None
    exclude: list[str] | None = None


@router.put("/facets/{facet_id}")
def update_facet(facet_id: str, payload: FacetUpdateRequest, response: Response, session: Session = Depends(get_db)):
    fd = FACET_DEFINITIONS_BY_ID.get(facet_id)
    if fd is None:
        raise HTTPException(status_code=404, detail=f"unknown facet_id: {facet_id!r}")
    if not fd.available:
        response.status_code = 422
        return {"detail": fd.unavailable_reason}

    now = to_naive_utc(datetime.now(timezone.utc))
    row = session.query(FounderFacetRecord).filter_by(facet_id=facet_id).first()
    existing = json.loads(row.values_json) if (row is not None and row.values_json) else {}
    include = payload.include if payload.include is not None else list(existing.get("include") or [])
    exclude = payload.exclude if payload.exclude is not None else list(existing.get("exclude") or [])
    mode = "off" if not include and not exclude else "active"
    values_json = json.dumps({"include": include, "exclude": exclude})

    if row is None:
        row = FounderFacetRecord(facet_id=facet_id, mode=mode, values_json=values_json, updated_at=now)
        session.add(row)
    else:
        row.mode = mode
        row.values_json = values_json
        row.updated_at = now
    session.commit()

    return {"facet_id": facet_id, "mode": mode, "include": include, "exclude": exclude}


# --------------------------------------------------------------------------
# C1: saved views
# --------------------------------------------------------------------------


@router.get("/saved-views")
def list_saved_views_route(session: Session = Depends(get_db)):
    return {"views": list_saved_views(session)}


class SavedViewCreateRequest(BaseModel):
    name: str
    facets: dict[str, Any] = {}
    search_query: str | None = None
    is_default: bool = False


@router.post("/saved-views")
def create_saved_view_route(payload: SavedViewCreateRequest, session: Session = Depends(get_db)):
    now = to_naive_utc(datetime.now(timezone.utc))
    return create_saved_view(
        session,
        name=payload.name,
        facets=payload.facets,
        search_query=payload.search_query,
        is_default=payload.is_default,
        now=now,
    )


class SavedViewUpdateRequest(BaseModel):
    name: str | None = None
    facets: dict[str, Any] | None = None
    search_query: str | None = None
    is_default: bool | None = None


@router.put("/saved-views/{view_id}")
def update_saved_view_route(view_id: str, payload: SavedViewUpdateRequest, session: Session = Depends(get_db)):
    now = to_naive_utc(datetime.now(timezone.utc))
    result = update_saved_view(
        session,
        view_id,
        name=payload.name,
        facets=payload.facets,
        search_query=payload.search_query,
        is_default=payload.is_default,
        now=now,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"unknown saved view: {view_id!r}")
    return result


@router.delete("/saved-views/{view_id}")
def delete_saved_view_route(view_id: str, session: Session = Depends(get_db)):
    ok = delete_saved_view(session, view_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"unknown saved view: {view_id!r}")
    return {"id": view_id, "status": "deleted"}


# --------------------------------------------------------------------------
# C4: hidden-reasons audit
# --------------------------------------------------------------------------


@router.get("/hidden-reasons")
def hidden_reasons_route(request: Request, session: Session = Depends(get_db)):
    filter_settings = _load_filter_settings(session)
    facet_settings = _load_facet_settings(session)
    truth_graph = _truth_graph_from_request(request)
    counts: dict[str, int] = {}
    for opportunities in _opportunity_batches(_opportunity_query(session)):
        contexts = build_filter_contexts(session, truth_graph, opportunities)
        partial = hidden_reasons_audit(contexts, filter_settings, facet_settings, truth_graph)
        for reason, count in partial.items():
            counts[reason] = counts.get(reason, 0) + count
    return {"reasons": [{"reason": reason, "count": count} for reason, count in sorted(counts.items())]}


class UnhideByReasonRequest(BaseModel):
    reason: str


@router.post("/hidden-reasons/unhide")
def unhide_by_reason_route(payload: UnhideByReasonRequest, session: Session = Depends(get_db)):
    now = to_naive_utc(datetime.now(timezone.utc))
    ok = unhide_by_reason(session, payload.reason, now)
    if not ok:
        raise HTTPException(status_code=404, detail=f"unrecognised reason: {payload.reason!r}")
    return {"reason": payload.reason, "status": "unhidden"}


@router.get("/opportunities")
def list_opportunities(
    request: Request,
    track: str | None = None,
    decision: str | None = None,
    min_score: float | None = None,
    since: str | None = None,
    q: str | None = None,
    include_hidden: bool = False,
    page: int = 1,
    page_size: int = 25,
    session: Session = Depends(get_db),
):
    query = _opportunity_query(session)
    if track:
        query = query.filter(OpportunityRecord.track == track)
    if since:
        query = query.filter(OpportunityRecord.created_at >= since)

    # BRIEF-FR-006 C2: full-text search replaces the old title/organization
    # `ilike` match. `search_relevance` (id -> ts_rank) stays empty unless a
    # search is active; everything downstream of this block (facet/filter
    # application via `apply_filters`, `hidden_count`) is unchanged and runs
    # against whatever `opportunities` ends up holding, so a search plus an
    # active exclusion facet naturally returns their intersection and still
    # counts the excluded rows. `search_message` is set only for genuinely
    # unparseable input (api.search.is_query_unparseable) -- never for a
    # query that legitimately matches zero rows -- and the response is an
    # empty result, never a 500, either way.
    search_relevance: dict[str, float] = {}
    search_message: str | None = None
    if q:
        if is_query_unparseable(session, q):
            search_message = "search query has no searchable terms"
            query = query.filter(False)
        else:
            hits = search_opportunity_ids(session, q)
            search_relevance = {hit.opportunity_id: hit.relevance for hit in hits}
            if search_relevance:
                query = query.filter(OpportunityRecord.id.in_(search_relevance.keys()))
            else:
                query = query.filter(False)

    filter_settings = _load_filter_settings(session)
    facet_settings = _load_facet_settings(session)
    truth_graph = _truth_graph_from_request(request)
    loaded_pack = request.app.state.loaded_truth_pack
    scan_filter_settings = filter_settings
    lightweight_prefiltered = (
        not include_hidden
        and decision is None
        and min_score is None
        and loaded_pack is not None
        and _can_lightweight_prefilter_hidden(filter_settings, facet_settings)
        and _can_lightweight_rank(filter_settings)
    )
    hidden_count = 0
    if lightweight_prefiltered:
        hidden_ids = _lightweight_hidden_ids(query, truth_graph, filter_settings)
        hidden_count = len(hidden_ids)
        # The only active hide-mode filters have already been applied. Disable
        # them during the lightweight rank pass so descriptions stay deferred.
        scan_filter_settings = dict(filter_settings)
        for filter_id in ("red_lines", "excluded_industries"):
            row = filter_settings.get(filter_id)
            definition = FILTER_DEFINITIONS_BY_ID[filter_id]
            scan_filter_settings[filter_id] = FilterSettingsRow(
                enabled=False,
                mode=row.mode if row is not None else definition.default_mode,
                params=row.params if row is not None else dict(definition.default_params),
            )
        query = query.options(defer(OpportunityRecord.description))

    ranked: list[dict[str, Any]] = []
    if lightweight_prefiltered:
        lightweight_rows = (
            query.with_entities(
                OpportunityRecord.id,
                OpportunityRecord.track,
                OpportunityRecord.title,
                OpportunityRecord.title_family,
                OpportunityRecord.posted_date,
                MatchEvaluationRecord.fit_score,
                MatchEvaluationRecord.dimension_scores_json,
            )
            .outerjoin(
                MatchEvaluationRecord,
                and_(
                    MatchEvaluationRecord.opportunity_id == OpportunityRecord.id,
                    MatchEvaluationRecord.truth_pack_hash == loaded_pack.truth_pack_hash,
                ),
            )
            .all()
        )
        track_rank = _filter_enabled_mode("track_preference", filter_settings) == (True, "rank_only")
        target_rank = _filter_enabled_mode("target_roles", filter_settings) == (True, "rank_only")
        premium_rank = _filter_enabled_mode("premium_fulltime_onsite", filter_settings) == (True, "rank_only")
        preferred_track = _founder_track_preference(truth_graph) if track_rank else None
        target_families = _founder_target_role_families(truth_graph) if target_rank else frozenset()
        normalized_families: dict[str, str] = {}
        for row in lightweight_rows:
            if row.id in hidden_ids:
                continue
            rank_penalty = 0
            if preferred_track is not None and row.track.casefold() != preferred_track:
                rank_penalty += 1
            if target_families:
                family = row.title_family
                if family is None:
                    family = normalized_families.get(row.title)
                    if family is None:
                        family = normalize_title(row.title)[0]
                        normalized_families[row.title] = family
                if family not in target_families:
                    rank_penalty += 1
            if premium_rank and row.dimension_scores_json and "premium_shortfall" in row.dimension_scores_json:
                dimensions = unpack_dimension_scores(row.dimension_scores_json)
                if any(
                    dim.get("dimension_name") == "compensation_fit"
                    and "premium_shortfall" in (dim.get("signal_tags") or [])
                    for dim in dimensions
                ):
                    rank_penalty += 1
            ranked.append(
                {
                    "id": row.id,
                    "fit_score": row.fit_score,
                    "posted_date": row.posted_date,
                    "_rank_penalty": rank_penalty,
                }
            )
    else:
        for opportunities in _opportunity_batches(query):
            contexts = _ranking_filter_contexts(
                session, truth_graph, opportunities, scan_filter_settings, facet_settings
            )
            for opp, ctx in zip(opportunities, contexts):
                opp_decision = ctx.decision
                fit_score = ctx.fit_score

                if decision and opp_decision != decision:
                    continue
                if min_score is not None and (fit_score is None or fit_score < min_score):
                    continue

                outcome = apply_filters(ctx, scan_filter_settings)
                facet_outcome = apply_facets(ctx, facet_settings)
                combined_hidden_by = outcome.hidden_by + [f"facet:{facet_id}" for facet_id in facet_outcome.hidden_by]
                if combined_hidden_by:
                    hidden_count += 1
                    if not include_hidden:
                        continue
                ranked.append(
                    {
                        "id": opp.id,
                        "fit_score": fit_score,
                        "posted_date": opp.posted_date,
                        "_rank_penalty": outcome.rank_penalty,
                    }
                )

    # Rank-penalty tier first (contract section 4: demoted items sort after
    # non-demoted ones at equal score, and never reorder within a tier).
    # Below that tier: with an active search, BRIEF-FR-006 C2's ranking
    # formula (relevance x fit, `api.search.rank_key`) descending -- this
    # changes row *order* only; `decision`/`fit_score` themselves are read
    # here, never written (see `api.search.rank_key`'s docstring and
    # `api/test_search.py::NoReJudgementTest`). Without an active search, the
    # pre-existing key is unchanged: fit_score descending, nulls last, then
    # posted_date descending, then id.
    if q and search_relevance:
        ranked.sort(
            key=lambda r: (
                r["_rank_penalty"],
                -rank_key(search_relevance.get(r["id"], 0.0), r["fit_score"]),
                _posted_date_sort_key(r["posted_date"]),
                r["id"],
            )
        )
    else:
        ranked.sort(
            key=lambda r: (
                r["_rank_penalty"],
                r["fit_score"] is None,
                -(r["fit_score"] or 0),
                _posted_date_sort_key(r["posted_date"]),
                r["id"],
            )
        )
    total = len(ranked)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    page_ids = [row["id"] for row in ranked[start : start + page_size]]

    page_items: list[dict[str, Any]] = []
    if page_ids:
        page_opportunities = _opportunity_query(session).filter(OpportunityRecord.id.in_(page_ids)).all()
        by_id = {opp.id: opp for opp in page_opportunities}
        page_opportunities = [by_id[opportunity_id] for opportunity_id in page_ids]
        page_contexts = build_filter_contexts(session, truth_graph, page_opportunities)
        family_sizes = _family_sizes(session, [opp.family_key for opp in page_opportunities])
        action_states = _batch_action_states(session, page_ids)
        feedback_labels = _batch_feedback_labels(session, page_ids)
        for opp, ctx in zip(page_opportunities, page_contexts):
            outcome = apply_filters(ctx, filter_settings)
            facet_outcome = apply_facets(ctx, facet_settings)
            combined_hidden_by = outcome.hidden_by + [f"facet:{facet_id}" for facet_id in facet_outcome.hidden_by]
            row = {
                "id": opp.id,
                "title": opp.title,
                "organization": opp.organization,
                "source_id": opp.source_id,
                "source_url": opp.source_url,
                "track": opp.track,
                "decision": ctx.decision,
                "fit_score": ctx.fit_score,
                "top_reasons": top_reasons_from_list(ctx.reasons),
                "deadline": opp.deadline,
                "posted_date": opp.posted_date,
                "is_stale": bool(opp.is_stale),
                "action_state": action_states.get(opp.id),
                "feedback_label": feedback_labels.get(opp.id),
                "hidden_by": combined_hidden_by,
                "flagged_by": outcome.flagged_by,
            }
            row.update(serialize_opportunity_extraction_fields(opp, family_sizes.get(opp.family_key)))
            page_items.append(row)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "hidden_count": hidden_count,
        "items": page_items,
        "message": search_message,
    }


def _posted_date_sort_key(value: str | None) -> tuple[int, Any]:
    """Sort helper: later dates sort first (ascending key), missing/unparseable
    dates sort last."""
    if not value:
        return (1, "")
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return (1, "")
    return (0, -(parsed.toordinal()))


def _build_opportunity_detail(session: Session, opp: OpportunityRecord) -> dict[str, Any]:
    provenances = session.query(FieldProvenanceRecord).filter_by(opportunity_id=opp.id).all()
    evaluation = _latest_evaluation(session, opp.id)

    qualification: dict[str, Any] = {"decision": None, "constraints": []}
    scoring: dict[str, Any] = {
        "fit_score": None,
        "dimension_scores": [],
        "strengths": [],
        "gaps": [],
        "unknowns": [],
        "uncertainty_penalty": 0.0,
        "explanation": "",
        "policy_version": None,
        "evaluated_at": None,
        "truth_pack_hash": None,
    }
    if evaluation is not None:
        reasons = unpack_reasons(evaluation.reasons_json)
        dims = unpack_dimension_scores(evaluation.dimension_scores_json)
        # `evaluation_detail_json` is a real, unconditional column on
        # MatchEvaluationRecord (nullable -- see storage/models.py). Read it
        # directly: if the attribute were ever missing that would be a
        # schema regression, and a `getattr` default would silently turn
        # that loud failure into a quietly empty checklist instead.
        detail = unpack_evaluation_detail(evaluation.evaluation_detail_json)
        # The column is nullable because rows persisted before it existed
        # have no detail payload (`evaluation_detail_json IS NULL`). That is
        # legitimate backward compatibility for real historical data, not
        # defensiveness about the schema -- so strengths/gaps/unknowns fall
        # back to a derivation from `reasons_json` only for such rows.
        fallback_strengths, fallback_gaps, fallback_unknowns = strengths_gaps_unknowns_from_reasons(reasons)

        qualification = {
            "decision": evaluation.qualification_decision,
            "constraints": [serialize_constraint(c) for c in detail["hard_constraints"]],
        }
        scoring = {
            "fit_score": evaluation.fit_score,
            "dimension_scores": [serialize_dimension_score(d) for d in dims],
            "strengths": detail["strengths"] or fallback_strengths,
            "gaps": detail["gaps"] or fallback_gaps,
            "unknowns": detail["unknowns"] or fallback_unknowns,
            "uncertainty_penalty": detail["uncertainty_penalty"],
            "explanation": detail["explanation"],
            "policy_version": evaluation.policy_version,
            "evaluated_at": _iso(evaluation.evaluated_at),
            "truth_pack_hash": evaluation.truth_pack_hash,
        }

    evidence_links = sorted({p.raw_pointer for p in provenances if p.raw_pointer})

    action_history = [
        {
            "action_id": a.id,
            "action_status": a.action_status,
            "execution_mode": a.execution_mode,
            "created_at": _iso(a.created_at),
            "updated_at": _iso(a.updated_at),
            "notes": a.blocker_reason,
        }
        for a in session.query(OutboundActionRecordModel)
        .filter_by(opportunity_id=opp.id)
        .order_by(OutboundActionRecordModel.created_at.asc())
        .all()
    ]

    feedback_history = [
        {
            "id": f.id,
            "feedback_label": f.feedback_label,
            "structured_reason": f.structured_reason,
            "notes": f.notes,
            "created_at": _iso(f.created_at),
        }
        for f in session.query(FounderFeedbackRecord)
        .filter_by(opportunity_id=opp.id)
        .order_by(FounderFeedbackRecord.created_at.asc())
        .all()
    ]

    family_size = None
    if opp.family_key:
        family_size = _family_sizes(session, [opp.family_key]).get(opp.family_key)

    detail_payload: dict[str, Any] = {
        "id": opp.id,
        "title": opp.title,
        "organization": opp.organization,
        "source_id": opp.source_id,
        "source_url": opp.source_url,
        "track": opp.track,
        "description": opp.description,
        "deadline": opp.deadline,
        "posted_date": opp.posted_date,
        "is_stale": bool(opp.is_stale),
        "reverified_at": _iso(opp.reverified_at),
        "fields": [
            {
                "field_name": p.field_name,
                "value": p.normalized_value,
                "raw_value": p.raw_value,
                "derivation_type": p.derivation_type,
                "raw_pointer": p.raw_pointer,
                "rule_id": p.rule_id,
                "record_checksum": p.record_checksum,
            }
            for p in provenances
        ],
        "qualification": qualification,
        "scoring": scoring,
        "evidence_links": evidence_links,
        "action_history": action_history,
        "feedback_history": feedback_history,
    }
    detail_payload.update(serialize_opportunity_extraction_fields(opp, family_size))
    return detail_payload


# --------------------------------------------------------------------------
# "New since you last looked" (BRIEF-FR-006 E4)
# --------------------------------------------------------------------------
#
# founder_opportunity_views (storage/models.py::FounderOpportunityViewRecord)
# already gets one row per opportunity the founder opens (see get_opportunity
# below, which is the only writer -- unchanged by this deliverable). "When
# the founder last looked at the feed" is taken here as the single most
# recent viewed_at across every such row, regardless of which opportunity it
# was for: any opportunity first ingested (OpportunityRecord.created_at,
# the same "how recent is this row" column api/routes_api.py's
# dashboard_daily already uses) after that instant is "new since you last
# looked". Named as an assumption in this work order's report -- the model
# itself has no single "feed-level" viewed_at column to read instead.
#
# This is purely additive/read-only: it never writes decision, fit_score, or
# hidden state, and marking a row seen (get_opportunity, below) never
# touches them either -- both endpoints only ever read/write
# founder_opportunity_views.viewed_at.
#
# Registered BEFORE `/opportunities/{opportunity_id}` below: FastAPI/Starlette
# matches routes in registration order, and "new-since-last-view" would
# otherwise be swallowed as an `opportunity_id` path value by that route.


def _last_feed_viewed_at(session: Session) -> datetime | None:
    return session.query(func.max(FounderOpportunityViewRecord.viewed_at)).scalar()


@router.get("/opportunities/new-since-last-view")
def opportunities_new_since_last_view(session: Session = Depends(get_db)):
    last_viewed_at = _last_feed_viewed_at(session)

    query = session.query(OpportunityRecord.id, OpportunityRecord.title, OpportunityRecord.created_at)
    if last_viewed_at is not None:
        query = query.filter(OpportunityRecord.created_at > last_viewed_at)
    rows = query.order_by(OpportunityRecord.created_at.desc()).all()

    return {
        "last_viewed_at": _iso(last_viewed_at),
        "count": len(rows),
        "new_opportunities": [
            {"id": r.id, "title": r.title, "created_at": _iso(r.created_at)} for r in rows
        ],
    }


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: str, session: Session = Depends(get_db)):
    opp = session.query(OpportunityRecord).filter_by(id=opportunity_id).first()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    detail = _build_opportunity_detail(session, opp)

    view = FounderOpportunityViewRecord(
        id=f"view-{uuid.uuid4().hex[:16]}",
        opportunity_id=opp.id,
        viewed_at=datetime.now(timezone.utc),
    )
    session.add(view)
    session.commit()

    return detail


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------

def _opportunity_to_domain(opp: OpportunityRecord, provenances: list[FieldProvenanceRecord]) -> Opportunity:
    skills: tuple[str, ...] = ()
    for p in provenances:
        if p.field_name == "skills" and p.normalized_value:
            try:
                parsed = json.loads(p.normalized_value)
                if isinstance(parsed, list):
                    skills = tuple(str(s) for s in parsed)
                    break
            except (json.JSONDecodeError, TypeError):
                skills = tuple(s.strip() for s in p.normalized_value.split(",") if s.strip())
                break

    return Opportunity(
        id=opp.id,
        track=Track(opp.track),
        source=opp.source_id,
        source_url=opp.source_url,
        source_id=opp.source_id,
        organization=opp.organization,
        title=opp.title,
        description=opp.description,
        skills=skills,
        content_hash=opp.content_hash,
    )


def _artifact_filename(kind: str, opportunity_id: str, ext: str) -> str:
    return f"{kind}-{opportunity_id}.{ext}"


def _validate_template_param(template: str | None) -> str:
    """`template` defaults to Classic; an unrecognized name is a 422, never
    a silent fallback that serves a different document than the founder
    asked for (BRIEF-FR-006 D2 requirement 2)."""
    if not template:
        return "classic"
    normalized = template.casefold()
    if normalized not in TEMPLATES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown template {template!r}; valid: {sorted(TEMPLATES)}",
        )
    return normalized


def _compile_artifact_or_response(
    request: Request, opportunity_id: str, kind: str, session: Session,
) -> tuple[Any, str] | Response:
    """Compiles and validates the artifact. Returns `(artifact,
    truth_pack_hash)` on success, or a `Response` (412/409) for the caller
    to return unchanged -- a 409 returned from here must never be handed to
    `artifact_cache.store()` (BRIEF-FR-006 D2 requirement 3)."""
    opp = session.query(OpportunityRecord).filter_by(id=opportunity_id).first()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    loaded_pack = request.app.state.loaded_truth_pack
    if loaded_pack is None:
        reason = request.app.state.truth_pack_error or "no truth pack loaded"
        return Response(
            status_code=412,
            media_type="application/json",
            content=json.dumps({"detail": "no truth pack loaded", "reason": reason}),
        )

    provenances = session.query(FieldProvenanceRecord).filter_by(opportunity_id=opp.id).all()
    domain_opp = _opportunity_to_domain(opp, provenances)

    compiler = EmploymentArtifactCompiler()
    compiled_at = datetime.now(timezone.utc).date().isoformat()
    if kind == "cv":
        artifact = compiler.compile_tailored_cv(domain_opp, loaded_pack.graph, compiled_at=compiled_at)
    else:
        artifact = compiler.compile_cover_letter(domain_opp, loaded_pack.graph, compiled_at=compiled_at)

    # ADR-0014 dispatch (NARRATIVE claims -> validate_narrative, everything
    # else -> validate_claim): shared with matching/test_artifacts_e2e.py and
    # matching/test_compiler.py via matching.artifact_validation, so the
    # tests exercise this exact production logic rather than a hand-copied
    # mirror of it (BRIEF-FR-005 D1 council remediation, defect 4b).
    validator = ClaimValidator(loaded_pack.graph)
    findings = validate_artifact_claims(artifact, validator)

    if findings:
        logger.info(
            "artifact claim validation rejected",
            extra={
                "component": "api.artifacts",
                "extra_data": {"opportunity_id": opportunity_id, "kind": kind, "finding_count": len(findings)},
            },
        )
        # No docx/pdf is ever built past this point, and this Response is
        # never passed to artifact_cache.store() by any caller below.
        return Response(
            status_code=409,
            media_type="application/json",
            content=json.dumps({"detail": "claim validation failed", "findings": findings}),
        )

    return artifact, loaded_pack.truth_pack_hash


def _serve_artifact(
    request: Request,
    opportunity_id: str,
    kind: str,
    fmt: str,
    session: Session,
    template: str | None,
    inline: bool,
) -> Response:
    """Shared DOCX/PDF path: validates the template, serves a cache hit
    without recompiling, and otherwise compiles+validates+exports+caches.
    `fmt` is `"docx"` or `"pdf"`; `inline` controls
    `Content-Disposition` (PDF preview uses `inline`, every download uses
    `attachment` -- BRIEF-FR-006 D2 requirement 1)."""
    template_id = _validate_template_param(template)
    media_type = DOCX_MEDIA_TYPE if fmt == "docx" else PDF_MEDIA_TYPE
    cache_kind = artifact_cache.docx_kind(kind) if fmt == "docx" else artifact_cache.pdf_kind(kind)
    filename = _artifact_filename(kind, opportunity_id, fmt)
    disposition = "inline" if inline else "attachment"

    opp = session.query(OpportunityRecord).filter_by(id=opportunity_id).first()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    loaded_pack = request.app.state.loaded_truth_pack
    if loaded_pack is None:
        reason = request.app.state.truth_pack_error or "no truth pack loaded"
        return Response(
            status_code=412,
            media_type="application/json",
            content=json.dumps({"detail": "no truth pack loaded", "reason": reason}),
        )

    key = artifact_cache.cache_key(opportunity_id, loaded_pack.truth_pack_hash, template_id, cache_kind)
    logger.info(
        "artifact cache lookup",
        extra={"component": "api.artifacts", "extra_data": {"cache_key": key, "kind": cache_kind}},
    )
    cached = artifact_cache.get(session, opportunity_id, loaded_pack.truth_pack_hash, template_id, cache_kind)
    if cached is not None:
        cached_content_type, cached_payload = cached
        return Response(
            content=cached_payload,
            media_type=cached_content_type,
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

    result = _compile_artifact_or_response(request, opportunity_id, kind, session)
    if isinstance(result, Response):
        return result
    artifact, truth_pack_hash = result

    if fmt == "docx":
        content = BinaryArtifactExporter.export_to_docx(artifact, template=template_id)
    else:
        content = BinaryArtifactExporter.export_to_pdf(artifact, template=template_id)

    artifact_cache.store(session, opportunity_id, truth_pack_hash, template_id, cache_kind, media_type, content)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/opportunities/{opportunity_id}/artifacts/cv.docx")
def get_cv_artifact(
    opportunity_id: str, request: Request, session: Session = Depends(get_db), template: str | None = None,
):
    return _serve_artifact(request, opportunity_id, "cv", "docx", session, template, inline=False)


@router.get("/opportunities/{opportunity_id}/artifacts/cover-letter.docx")
def get_cover_letter_artifact(
    opportunity_id: str, request: Request, session: Session = Depends(get_db), template: str | None = None,
):
    return _serve_artifact(request, opportunity_id, "cover-letter", "docx", session, template, inline=False)


@router.get("/opportunities/{opportunity_id}/artifacts/cv.pdf")
def get_cv_pdf_artifact(
    opportunity_id: str,
    request: Request,
    session: Session = Depends(get_db),
    template: str | None = None,
    download: bool = False,
):
    """Inline by default (BRIEF-FR-006 D2 requirement 1, embedded preview);
    `?download=true` returns the same bytes as `attachment` for saving."""
    return _serve_artifact(request, opportunity_id, "cv", "pdf", session, template, inline=not download)


@router.get("/opportunities/{opportunity_id}/artifacts/cover-letter.pdf")
def get_cover_letter_pdf_artifact(
    opportunity_id: str,
    request: Request,
    session: Session = Depends(get_db),
    template: str | None = None,
    download: bool = False,
):
    return _serve_artifact(request, opportunity_id, "cover-letter", "pdf", session, template, inline=not download)


@router.get("/opportunities/{opportunity_id}/artifacts/{kind}/omitted")
def get_artifact_omitted_items(
    opportunity_id: str,
    kind: str,
    request: Request,
    session: Session = Depends(get_db),
    template: str | None = None,
):
    """D1's "what was left out and why" data
    (`TailoredArtifact.omitted_items`), exposed as JSON so the drawer's
    artifacts panel can render it next to the PDF preview without parsing a
    binary document. Not cached -- it recompiles the same way
    `_compile_artifact_or_response` always has; only the exported document
    bytes are cached (BRIEF-FR-006 D2 requirement 3 concerns the document,
    not this metadata)."""
    if kind not in ("cv", "cover-letter"):
        raise HTTPException(status_code=404, detail="unknown artifact kind")
    template_id = _validate_template_param(template)

    result = _compile_artifact_or_response(request, opportunity_id, kind, session)
    if isinstance(result, Response):
        return result
    artifact, _truth_pack_hash = result

    return {
        "template": template_id,
        "omitted_items": [
            {
                "section_id": item.section_id,
                "text": item.text,
                "reason": item.reason,
                "claim_id": item.claim_id,
            }
            for item in artifact.omitted_items
        ],
    }


# --------------------------------------------------------------------------
# Feedback and actions
# --------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    label: str
    note: str | None = None


@router.post("/opportunities/{opportunity_id}/feedback")
def submit_feedback(
    opportunity_id: str,
    payload: FeedbackRequest,
    response: Response,
    session: Session = Depends(get_db),
):
    opp = session.query(OpportunityRecord).filter_by(id=opportunity_id).first()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    try:
        label = FeedbackLabel(payload.label)
    except ValueError:
        response.status_code = 422
        return {"detail": "unknown feedback label", "allowed": [item.value for item in FeedbackLabel]}

    service = FounderFeedbackService(StorageRepository(session))
    event = service.submit_feedback(opportunity_id=opportunity_id, label=label, notes=payload.note)

    return {
        "id": event.id,
        "opportunity_id": event.opportunity_id,
        "feedback_label": event.feedback_label.value,
        "structured_reason": event.structured_reason,
        "notes": event.notes,
        "created_at": event.created_at,
    }


class ActionRequest(BaseModel):
    type: str
    until: str | None = None


@router.post("/opportunities/{opportunity_id}/actions")
def submit_action(
    opportunity_id: str,
    payload: ActionRequest,
    response: Response,
    session: Session = Depends(get_db),
):
    opp = session.query(OpportunityRecord).filter_by(id=opportunity_id).first()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    now = datetime.now(timezone.utc)

    if payload.type == "dismiss":
        _upsert_triage_state(session, opportunity_id, "dismissed", None, now)
        return {
            "opportunity_id": opportunity_id,
            "action_state": "dismissed",
            "action_id": None,
            "until": None,
            "created_at": now.isoformat(),
        }

    if payload.type == "snooze":
        until_date = _parse_future_date(payload.until, now)
        if until_date is None:
            response.status_code = 422
            return {"detail": "snooze requires a future 'until' date"}
        _upsert_triage_state(session, opportunity_id, "snoozed", until_date, now)
        return {
            "opportunity_id": opportunity_id,
            "action_state": "snoozed",
            "action_id": None,
            "until": until_date.date().isoformat(),
            "created_at": now.isoformat(),
        }

    if payload.type == "mark_applied":
        evaluation = _latest_evaluation(session, opportunity_id)
        action_id = f"action-{uuid.uuid4().hex[:16]}"
        record = OutboundActionRecordModel(
            id=action_id,
            opportunity_id=opportunity_id,
            opportunity_content_hash=opp.content_hash,
            workspace="default",
            candidate_id="founder",
            track=opp.track,
            source=opp.source_id,
            adapter_name="founder_attested",
            adapter_version="1.0",
            execution_mode=ExecutionMode.DRY_RUN.value,
            qualification_decision=(evaluation.qualification_decision if evaluation else "uncertain"),
            match_score_snapshot=(evaluation.fit_score if evaluation else 0.0),
            artifact_ids_json="[]",
            artifact_hashes_json="[]",
            manifest_hash=hashlib.sha256(f"founder-attested:{opportunity_id}:{now.isoformat()}".encode()).hexdigest(),
            action_status=ActionStatus.SUBMITTED.value,
            # Unique per row, but no `idempotency_reservations` row is reserved
            # or consumed for a founder-attested manual action -- see the
            # `FeedbackAndActionTest` case that asserts the reservation table
            # row count is unchanged by this endpoint.
            idempotency_key=f"founder-attested:{opportunity_id}:{uuid.uuid4().hex}",
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        session.commit()
        return {
            "opportunity_id": opportunity_id,
            "action_state": "submitted",
            "action_id": action_id,
            "until": None,
            "created_at": now.isoformat(),
        }

    response.status_code = 422
    return {"detail": f"unknown action type: {payload.type!r}"}


def _parse_future_date(until: str | None, now: datetime) -> datetime | None:
    if not until:
        return None
    try:
        parsed = date.fromisoformat(until)
    except ValueError:
        return None
    parsed_dt = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
    if parsed_dt <= now:
        return None
    return parsed_dt


def _upsert_triage_state(session: Session, opportunity_id: str, state: str, snoozed_until: datetime | None, now: datetime) -> None:
    existing = session.query(FounderTriageStateRecord).filter_by(opportunity_id=opportunity_id).first()
    if existing is None:
        session.add(
            FounderTriageStateRecord(
                opportunity_id=opportunity_id,
                state=state,
                snoozed_until=snoozed_until,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        existing.state = state
        existing.snoozed_until = snoozed_until
        existing.updated_at = now
    session.commit()


# --------------------------------------------------------------------------
# Digest (BRIEF-FR-006 F3) -- exposes the file worker.digest.generate_digest
# (``python -m worker --digest``) already wrote to out/digest/. Read-only:
# this endpoint never generates a digest itself, only reads the latest one
# already on disk.
# --------------------------------------------------------------------------

@router.get("/digest/latest")
def digest_latest():
    from worker.digest import latest_digest

    digest = latest_digest()
    if digest is None:
        raise HTTPException(status_code=404, detail="no digest has been generated yet")
    return digest


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@router.get("/dashboard/daily")
def dashboard_daily(request: Request, days: int = 7, session: Session = Depends(get_db)):
    days = max(1, min(days, 90))
    high_fit_threshold = request.app.state.settings.high_fit_threshold
    today = datetime.now(timezone.utc).date()

    filter_settings = _load_filter_settings(session)
    truth_graph = _truth_graph_from_request(request)

    series = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        fetched = (
            session.query(func.coalesce(func.sum(SourcePollRunRecord.raw_ingested), 0))
            .filter(SourcePollRunRecord.started_at >= day_start, SourcePollRunRecord.started_at < day_end)
            .scalar()
        )
        unique_new = (
            session.query(func.count(OpportunityRecord.id))
            .filter(OpportunityRecord.created_at >= day_start, OpportunityRecord.created_at < day_end)
            .scalar()
        )
        evaluations_today = (
            session.query(MatchEvaluationRecord)
            .filter(MatchEvaluationRecord.evaluated_at >= day_start, MatchEvaluationRecord.evaluated_at < day_end)
            .all()
        )
        qualified = sum(1 for e in evaluations_today if e.qualification_decision == "qualified")
        high_fit = sum(1 for e in evaluations_today if e.fit_score is not None and e.fit_score >= high_fit_threshold)
        opened = (
            session.query(func.count(FounderOpportunityViewRecord.id))
            .filter(FounderOpportunityViewRecord.viewed_at >= day_start, FounderOpportunityViewRecord.viewed_at < day_end)
            .scalar()
        )
        labelled = (
            session.query(func.count(FounderFeedbackRecord.id))
            .filter(FounderFeedbackRecord.created_at >= day_start, FounderFeedbackRecord.created_at < day_end)
            .scalar()
        )
        applied = (
            session.query(func.count(OutboundActionRecordModel.id))
            .filter(
                OutboundActionRecordModel.created_at >= day_start,
                OutboundActionRecordModel.created_at < day_end,
                OutboundActionRecordModel.action_status == ActionStatus.SUBMITTED.value,
            )
            .scalar()
        )
        hidden_by_filters = 0
        day_query = _opportunity_query(session).filter(
            OpportunityRecord.created_at >= day_start,
            OpportunityRecord.created_at < day_end,
        )
        if _can_lightweight_prefilter_hidden(filter_settings, {}):
            hidden_by_filters = len(_lightweight_hidden_ids(day_query, truth_graph, filter_settings))
        else:
            for day_opportunities in _opportunity_batches(day_query):
                day_contexts = build_filter_contexts(session, truth_graph, day_opportunities)
                hidden_by_filters += sum(1 for ctx in day_contexts if apply_filters(ctx, filter_settings).hidden_by)

        series.append(
            {
                "date": day.isoformat(),
                "fetched": int(fetched or 0),
                "unique_new": int(unique_new or 0),
                "qualified": qualified,
                "high_fit": high_fit,
                "opened": int(opened or 0),
                "labelled": int(labelled or 0),
                "applied": int(applied or 0),
                "hidden_by_filters": hidden_by_filters,
            }
        )

    return {"days": days, "high_fit_threshold": high_fit_threshold, "series": series}


@router.get("/polls/{poll_id}/over-hiding")
def poll_over_hiding(poll_id: str, request: Request, session: Session = Depends(get_db)):
    """BRIEF-FR-006 C5: `api/facets.py::poll_hide_fraction_warnings` is the
    real, per-poll, filter-*and*-facet-aware "hid more than 10% of a poll's
    new rows" computation (see its own docstring and
    `PollHideFractionWarningTest`) -- but nothing called it, so the web side
    had derived a day-granular, filters-only approximation from
    `GET /api/dashboard/daily` instead (`web/lib/format/over-hiding.ts`,
    both divergences named in its own docstring). This route calls the real
    function directly against exactly the rows that specific poll inserted,
    so the returned figure is never an approximation of the underlying
    computation -- it *is* the underlying computation.

    A poll run has no `opportunity_id` foreign key back to the specific rows
    it inserted (frozen `storage/models.py` has no such column), so "the
    rows this poll inserted" is taken as every `OpportunityRecord` whose
    `created_at` falls within `[started_at, finished_at]` -- the same
    poll-window convention `dashboard_daily` already uses at day
    granularity, just narrowed to this one run's own window instead of a
    calendar day. `finished_at` is null for a run still in flight; `now` is
    used as the window's open end in that case.
    """
    poll = session.query(SourcePollRunRecord).filter_by(id=poll_id).first()
    if poll is None:
        raise HTTPException(status_code=404, detail="poll run not found")

    window_end = poll.finished_at or datetime.now(timezone.utc)
    new_opportunities = (
        session.query(OpportunityRecord)
        .filter(OpportunityRecord.created_at >= poll.started_at, OpportunityRecord.created_at <= window_end)
        .all()
    )
    truth_graph = _truth_graph_from_request(request)
    new_contexts = build_filter_contexts(session, truth_graph, new_opportunities)
    filter_settings = _load_filter_settings(session)
    facet_settings = _load_facet_settings(session)

    warnings = poll_hide_fraction_warnings(poll.inserted, new_contexts, filter_settings, facet_settings)
    return {"poll_id": poll.id, "poll_inserted": poll.inserted, "warnings": warnings}


# --------------------------------------------------------------------------
# Sources and worker
# --------------------------------------------------------------------------

@router.get("/manual-sources")
def manual_sources_route():
    """BRIEF-FR-006 C5: `opportunity/manual_sources.py::MANUAL_SOURCES` had
    no serving route, so the web side had transcribed it statically into
    `web/lib/data/manual-sources.ts` (drift risk named in that order's
    return notes -- and that transcription had already drifted, still
    listing `hacker_news_who_is_hiring`, which a later council review
    removed from this module because it is a fully automated, read-allowed
    adapter, not a manual fallback). This route serves the module's own
    tuple directly -- read-only, in-process, no network I/O of any kind
    (`ManualSource.deep_link` is pure string templating) -- so the founder's
    "Check manually" panel can never again silently diverge from the
    catalogue that actually governs which sources are manual-only."""
    return {
        "sources": [
            {
                "source_id": item.source_id,
                "name": item.name,
                "track": item.track.value,
                "opportunity_type": item.opportunity_type,
                "deep_link": item.deep_link(),
                "category": item.category,
                "policy_note": item.policy_note,
                "alert_route_available": item.alert_route_available,
                "alert_route_configured": item.alert_route_configured,
                "readiness_checklist": list(item.readiness_checklist),
            }
            for item in MANUAL_SOURCES
        ]
    }


TUTORING_VALID_STATUSES = {
    "not_started",
    "preparing_profile",
    "ready_to_apply",
    "applied",
    "approved",
    "rejected_unavailable",
}


def _derive_tutoring_next_action(status: str, checklist: dict[str, bool], total_items: int) -> str:
    if status == "not_started":
        return "Review platform requirements and draft profile bio"
    if status == "preparing_profile":
        completed = sum(1 for v in checklist.values() if v)
        if completed == total_items:
            return "Ready to apply — open canonical application link"
        return f"Complete remaining readiness items ({completed}/{total_items} done)"
    if status == "ready_to_apply":
        return "Open canonical application link and submit profile"
    if status == "applied":
        return "Monitor platform verification and email activation"
    if status == "approved":
        return "Profile live — active to receive student bookings"
    if status == "rejected_unavailable":
        return "Application closed or platform paused"
    return "Review platform requirements"


class TutoringPlatformUpdateRequest(BaseModel):
    status: str | None = None
    checklist: dict[str, bool] | None = None
    checklist_state: dict[str, bool] | None = None
    notes: str | None = None


@router.get("/tutoring/platforms")
def list_tutoring_platforms(session: Session = Depends(get_db)):
    """Return all platform_application tutoring platforms with readiness checklists and founder status."""
    cards = tutoring_platform_cards()
    filter_ids = [f"tutoring_platform_{c.source_id}" for c in cards]
    rows = {
        r.filter_id: r
        for r in session.query(FounderFilterSettingRecord).filter(
            FounderFilterSettingRecord.filter_id.in_(filter_ids)
        ).all()
    }

    platforms = []
    for card in cards:
        fid = f"tutoring_platform_{card.source_id}"
        row = rows.get(fid)
        persisted_data = json.loads(row.params_json) if row and row.params_json else {}
        status = persisted_data.get("status", "not_started")
        if status not in TUTORING_VALID_STATUSES:
            status = "not_started"
        checklist_state = persisted_data.get("checklist", {})
        normalized_checklist = {
            item: bool(checklist_state.get(item, False)) for item in card.readiness_checklist
        }
        next_action = _derive_tutoring_next_action(
            status, normalized_checklist, len(card.readiness_checklist)
        )
        platforms.append(
            {
                "id": card.source_id,
                "name": card.name,
                "acquisition_type": card.opportunity_type,
                "track": card.track.value,
                "canonical_url": card.deep_link(),
                "policy_posture": card.policy_note,
                "readiness_checklist": list(card.readiness_checklist),
                "checklist_state": normalized_checklist,
                "status": status,
                "next_action": next_action,
                "notes": persisted_data.get("notes", ""),
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            }
        )
    return {"platforms": platforms}


@router.put("/tutoring/platforms/{platform_id}")
def update_tutoring_platform(
    platform_id: str,
    payload: TutoringPlatformUpdateRequest,
    response: Response,
    session: Session = Depends(get_db),
):
    """Update activation status, checklist, or notes for a tutoring platform."""
    cards = {c.source_id: c for c in tutoring_platform_cards()}
    card = cards.get(platform_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"unknown tutoring platform_id: {platform_id!r}")

    if payload.status is not None and payload.status not in TUTORING_VALID_STATUSES:
        response.status_code = 422
        return {"detail": "invalid status", "allowed": sorted(TUTORING_VALID_STATUSES)}

    fid = f"tutoring_platform_{platform_id}"
    row = session.query(FounderFilterSettingRecord).filter_by(filter_id=fid).first()
    now = to_naive_utc(datetime.now(timezone.utc))
    if row is None:
        row = FounderFilterSettingRecord(
            filter_id=fid,
            enabled=True,
            mode="tutoring",
            params_json=json.dumps({"status": "not_started", "checklist": {}, "notes": ""}),
            updated_at=now,
        )
        session.add(row)

    current_params = json.loads(row.params_json) if row.params_json else {}
    if payload.status is not None:
        current_params["status"] = payload.status
    ck = payload.checklist if payload.checklist is not None else payload.checklist_state
    if ck is not None:
        merged = current_params.get("checklist", {})
        merged.update({str(k): bool(v) for k, v in ck.items()})
        current_params["checklist"] = merged
    if payload.notes is not None:
        current_params["notes"] = payload.notes
    row.mode = "tutoring"
    row.params_json = json.dumps(current_params)
    row.updated_at = now
    session.commit()

    saved_status = current_params.get("status", "not_started")
    normalized_checklist = {
        item: bool(current_params.get("checklist", {}).get(item, False))
        for item in card.readiness_checklist
    }
    next_action = _derive_tutoring_next_action(
        saved_status, normalized_checklist, len(card.readiness_checklist)
    )
    return {
        "id": platform_id,
        "name": card.name,
        "acquisition_type": card.opportunity_type,
        "track": card.track.value,
        "canonical_url": card.deep_link(),
        "policy_posture": card.policy_note,
        "readiness_checklist": list(card.readiness_checklist),
        "checklist_state": normalized_checklist,
        "status": saved_status,
        "next_action": next_action,
        "notes": current_params.get("notes", ""),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/tutoring/profile-material")
def get_tutoring_profile_material(request: Request):
    """Serve verified, truth-locked founder profile material suitable for tutoring platform bios."""
    graph = _truth_graph_from_request(request)
    if graph is None:
        raise HTTPException(status_code=412, detail="no truth pack loaded")

    summaries = []
    skills = []
    languages = []
    evidence_ids = set()

    for p in graph._profiles.values():
        if isinstance(p, CareerProfile):
            summaries.extend(p.approved_summaries)
            evidence_ids.update(p.evidence_ids)
            for s in p.skills:
                prof = s.proficiency.value if hasattr(s.proficiency, "value") else (s.proficiency or "")
                skills.append({"name": s.name, "proficiency": prof})
                evidence_ids.update(s.evidence_ids)
            for lang in p.languages:
                prof = lang.proficiency.value if hasattr(lang.proficiency, "value") else (lang.proficiency or "")
                languages.append({"language": lang.language, "proficiency": prof})
                evidence_ids.update(lang.evidence_ids)

    return {
        "verified": True,
        "approved_summaries": list(summaries),
        "tutoring_skills": skills,
        "languages": languages,
        "evidence_ids": sorted(evidence_ids),
    }


@router.get("/sources/health")
def sources_health(session: Session = Depends(get_db)):
    registry = SourceRegistry()
    sources = []
    # SourceRegistry (opportunity/registry.py, out of D6's file scope) has no
    # public "list all sources" accessor -- only per-id lookups. `_sources`
    # is read-only here; nothing is mutated.
    for source_id, policy in registry._sources.items():
        last_run = (
            session.query(SourcePollRunRecord)
            .filter_by(source_id=source_id)
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        sources.append(
            {
                "source_id": source_id,
                "name": policy.name,
                "category": policy.category,
                "read_policy": "allowed" if policy.read_allowed else "disabled",
                "last_poll": _iso(last_run.started_at) if last_run else None,
                "last_status": last_run.status if last_run else None,
                "last_record_count": last_run.raw_ingested if last_run else None,
            }
        )
    return {"sources": sources}


@router.post("/worker/poll-now")
def poll_now(request: Request, session: Session = Depends(get_db)):
    registry = SourceRegistry()
    queue = BackgroundWorkerQueue(session)
    enqueued = []
    skipped = []
    for source_id in registry._sources:
        if registry.is_read_allowed(source_id):
            job_id = queue.enqueue_job("poll_source", {"source_id": source_id})
            enqueued.append({"source_id": source_id, "job_id": job_id})
        else:
            skipped.append({"source_id": source_id, "reason": "read_disabled_by_policy"})
    return {"enqueued": enqueued, "skipped": skipped}


# --------------------------------------------------------------------------
# Truth pack status / reload
# --------------------------------------------------------------------------

def _truth_status_payload(request: Request) -> dict[str, Any]:
    loaded_pack = request.app.state.loaded_truth_pack
    if loaded_pack is None:
        findings = list(request.app.state.truth_pack_findings or ["no truth pack loaded"])
        return {
            "loaded": False,
            "hash": None,
            "path": str(request.app.state.truth_pack_path_display),
            "validator": {
                "ok": False,
                # A missing pack is an expected deployment state, not a pack
                # that failed validation.  The web contract uses zero to
                # distinguish that state from a present-but-invalid pack.
                "error_count": 0 if request.app.state.truth_pack_missing else len(findings),
                "findings": findings,
            },
            "sections": [],
        }
    report = loaded_pack.report
    return {
        "loaded": True,
        "hash": loaded_pack.truth_pack_hash,
        "path": str(request.app.state.truth_pack_path_display),
        "validator": {
            "ok": report.valid,
            "error_count": len(report.findings),
            "findings": list(report.findings),
        },
        "sections": [
            {"section": name, "present": count > 0, "count": count}
            for name, count in report.section_counts
        ],
    }


def load_truth_pack_into_state(app: Any) -> None:
    """Load (or reload) the founder truth pack into `app.state`. Used both at
    app startup and by `POST /api/truth/reload`. Never logs pack contents."""
    settings = app.state.settings
    try:
        loaded = load_founder_pack(settings.truth_pack_path)
        app.state.loaded_truth_pack = loaded
        app.state.truth_pack_error = None
        app.state.truth_pack_findings = ()
        app.state.truth_pack_missing = False
    except TruthPackMissing as error:
        app.state.loaded_truth_pack = None
        app.state.truth_pack_error = str(error)
        app.state.truth_pack_findings = (str(error),)
        app.state.truth_pack_missing = True
    except TruthPackInvalid as error:
        app.state.loaded_truth_pack = None
        app.state.truth_pack_error = str(error)
        app.state.truth_pack_findings = tuple(error.findings)
        app.state.truth_pack_missing = False


@router.get("/truth/status")
def truth_status(request: Request):
    return _truth_status_payload(request)


@router.post("/truth/reload")
def truth_reload(request: Request):
    load_truth_pack_into_state(request.app)
    return _truth_status_payload(request)
