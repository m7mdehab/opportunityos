"""Every non-auth route. Gated globally by `require_session` at the
APIRouter level so a new route added here cannot ship unguarded."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.logging import get_logger
from feedback.models import FeedbackLabel
from feedback.service import FounderFeedbackService
from matching.artifact_validation import validate_artifact_claims
from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from opportunity.models import Opportunity, Track
from opportunity.registry import SourceRegistry
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
    OpportunityRecord,
    OutboundActionRecordModel,
    SourcePollRunRecord,
)
from storage.repository import StorageRepository
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack
from truth.validator import ClaimValidator
from worker.queue import BackgroundWorkerQueue

from .deps import get_db, get_repository, require_session
from .facets import (
    FACET_DEFINITIONS_BY_ID,
    FacetSettingsRow,
    apply_facets,
    facet_payload,
    hidden_reasons_audit,
    unhide_by_reason,
)
from .filters import (
    FILTER_DEFINITIONS,
    FILTER_DEFINITIONS_BY_ID,
    FILTER_MODES,
    FilterSettingsRow,
    ParamValidationError,
    affected_count as filter_affected_count,
    apply_filters,
    build_filter_contexts,
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
    strengths_gaps_unknowns_from_reasons,
    top_reasons_from_list,
    unpack_dimension_scores,
    unpack_evaluation_detail,
    unpack_reasons,
)

logger = get_logger("api.routes")

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


def _latest_action_state(session: Session, opportunity_id: str) -> str | None:
    triage = session.query(FounderTriageStateRecord).filter_by(opportunity_id=opportunity_id).first()
    if triage is not None:
        if triage.state == "snoozed":
            snoozed_until = _as_aware_utc(triage.snoozed_until)
            snooze_still_active = snoozed_until is None or snoozed_until > datetime.now(timezone.utc)
            if snooze_still_active:
                return "snoozed"
            # Expired snooze: no longer suppress the opportunity from the
            # feed -- fall through to check for a submitted action instead
            # of reporting a stale "snoozed" state forever.
        else:
            return triage.state
    submitted = (
        session.query(OutboundActionRecordModel)
        .filter_by(opportunity_id=opportunity_id, action_status=ActionStatus.SUBMITTED.value)
        .order_by(OutboundActionRecordModel.created_at.desc())
        .first()
    )
    if submitted is not None:
        return "submitted"
    return None


def _latest_feedback_label(session: Session, opportunity_id: str) -> str | None:
    fb = (
        session.query(FounderFeedbackRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(FounderFeedbackRecord.created_at.desc())
        .first()
    )
    return fb.feedback_label if fb is not None else None


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


@router.get("/filters")
def list_filters(request: Request, session: Session = Depends(get_db)):
    settings = _load_filter_settings(session)
    truth_graph = _truth_graph_from_request(request)
    contexts = build_filter_contexts(session, truth_graph, session.query(OpportunityRecord).all())

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
                "affected_count": filter_affected_count(fd, params, contexts),
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
    contexts = build_filter_contexts(session, truth_graph, session.query(OpportunityRecord).all())
    return {
        "filter_id": row.filter_id,
        "enabled": row.enabled,
        "mode": row.mode,
        "params": params,
        "affected_count": filter_affected_count(fd, params, contexts),
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


@router.get("/facets")
def list_facets(request: Request, session: Session = Depends(get_db)):
    facet_settings = _load_facet_settings(session)
    filter_settings = _load_filter_settings(session)
    truth_graph = _truth_graph_from_request(request)
    opportunities = session.query(OpportunityRecord).all()
    contexts = build_filter_contexts(session, truth_graph, opportunities)
    # A facet only ever narrows what the policy filters already show -- the
    # same base set `GET /api/opportunities` returns without
    # `include_hidden`, before any facet narrows it further.
    visible = [ctx for ctx in contexts if not apply_filters(ctx, filter_settings).hidden_by]
    return {"facets": facet_payload(visible, facet_settings)}


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
    opportunities = session.query(OpportunityRecord).all()
    contexts = build_filter_contexts(session, truth_graph, opportunities)
    counts = hidden_reasons_audit(contexts, filter_settings, facet_settings, truth_graph)
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
    query = session.query(OpportunityRecord)
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
            opportunities: list[OpportunityRecord] = []
        else:
            hits = search_opportunity_ids(session, q)
            search_relevance = {hit.opportunity_id: hit.relevance for hit in hits}
            if search_relevance:
                query = query.filter(OpportunityRecord.id.in_(search_relevance.keys()))
                opportunities = query.all()
            else:
                opportunities = []
    else:
        opportunities = query.all()

    filter_settings = _load_filter_settings(session)
    facet_settings = _load_facet_settings(session)
    truth_graph = _truth_graph_from_request(request)
    contexts = build_filter_contexts(session, truth_graph, opportunities)

    rows: list[dict[str, Any]] = []
    hidden_count = 0
    for opp, ctx in zip(opportunities, contexts):
        opp_decision = ctx.decision
        fit_score = ctx.fit_score

        if decision and opp_decision != decision:
            continue
        if min_score is not None and (fit_score is None or fit_score < min_score):
            continue

        outcome = apply_filters(ctx, filter_settings)
        # C1 composition point: a facet only ever adds to `hidden_by` --
        # never touches `decision`/`fit_score`/`flagged_by`/rank order. Facet
        # hits are namespaced `facet:<facet_id>` so the UI (and the C4 audit)
        # can tell a policy-filter hit from a facet hit in the same list.
        facet_outcome = apply_facets(ctx, facet_settings)
        combined_hidden_by = outcome.hidden_by + [f"facet:{facet_id}" for facet_id in facet_outcome.hidden_by]
        if combined_hidden_by:
            hidden_count += 1
            if not include_hidden:
                continue

        rows.append(
            {
                "id": opp.id,
                "title": opp.title,
                "organization": opp.organization,
                "source_id": opp.source_id,
                "source_url": opp.source_url,
                "track": opp.track,
                "decision": opp_decision,
                "fit_score": fit_score,
                "top_reasons": top_reasons_from_list(ctx.reasons),
                "deadline": opp.deadline,
                "posted_date": opp.posted_date,
                "is_stale": bool(opp.is_stale),
                "action_state": _latest_action_state(session, opp.id),
                "feedback_label": _latest_feedback_label(session, opp.id),
                "hidden_by": combined_hidden_by,
                "flagged_by": outcome.flagged_by,
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
        rows.sort(
            key=lambda r: (
                r["_rank_penalty"],
                -rank_key(search_relevance.get(r["id"], 0.0), r["fit_score"]),
                _posted_date_sort_key(r["posted_date"]),
                r["id"],
            )
        )
    else:
        rows.sort(
            key=lambda r: (
                r["_rank_penalty"],
                r["fit_score"] is None,
                -(r["fit_score"] or 0),
                _posted_date_sort_key(r["posted_date"]),
                r["id"],
            )
        )
    for r in rows:
        del r["_rank_penalty"]

    total = len(rows)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    page_items = rows[start : start + page_size]

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

    return {
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


def _artifact_filename(kind: str, opportunity_id: str) -> str:
    return f"{kind}-{opportunity_id}.docx"


def _compile_and_export(request: Request, opportunity_id: str, kind: str, session: Session) -> Response:
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
        # No docx is ever built past this point -- export_to_docx is not called.
        return Response(
            status_code=409,
            media_type="application/json",
            content=json.dumps({"detail": "claim validation failed", "findings": findings}),
        )

    docx_bytes = BinaryArtifactExporter.export_to_docx(artifact)
    filename = _artifact_filename(kind, opportunity_id)
    return Response(
        content=docx_bytes,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/opportunities/{opportunity_id}/artifacts/cv.docx")
def get_cv_artifact(opportunity_id: str, request: Request, session: Session = Depends(get_db)):
    return _compile_and_export(request, opportunity_id, "cv", session)


@router.get("/opportunities/{opportunity_id}/artifacts/cover-letter.docx")
def get_cover_letter_artifact(opportunity_id: str, request: Request, session: Session = Depends(get_db)):
    return _compile_and_export(request, opportunity_id, "cover-letter", session)


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
        day_opportunities = (
            session.query(OpportunityRecord)
            .filter(OpportunityRecord.created_at >= day_start, OpportunityRecord.created_at < day_end)
            .all()
        )
        day_contexts = build_filter_contexts(session, truth_graph, day_opportunities)
        hidden_by_filters = sum(1 for ctx in day_contexts if apply_filters(ctx, filter_settings).hidden_by)

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


# --------------------------------------------------------------------------
# Sources and worker
# --------------------------------------------------------------------------

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
        return {
            "loaded": False,
            "hash": None,
            "path": str(request.app.state.truth_pack_path_display),
            "validator": {
                "ok": False,
                "error_count": 1,
                "findings": list(request.app.state.truth_pack_findings or ["no truth pack loaded"]),
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
    except TruthPackMissing as error:
        app.state.loaded_truth_pack = None
        app.state.truth_pack_error = str(error)
        app.state.truth_pack_findings = (str(error),)
    except TruthPackInvalid as error:
        app.state.loaded_truth_pack = None
        app.state.truth_pack_error = str(error)
        app.state.truth_pack_findings = tuple(error.findings)


@router.get("/truth/status")
def truth_status(request: Request):
    return _truth_status_payload(request)


@router.post("/truth/reload")
def truth_reload(request: Request):
    load_truth_pack_into_state(request.app)
    return _truth_status_payload(request)
