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
from matching.binary_export import BinaryArtifactExporter
from matching.compiler_employment import EmploymentArtifactCompiler
from opportunity.models import Opportunity, Track
from opportunity.registry import SourceRegistry
from outbound.models import ActionStatus, ExecutionMode
from storage.models import (
    FieldProvenanceRecord,
    FounderFeedbackRecord,
    FounderOpportunityViewRecord,
    FounderTriageStateRecord,
    MatchEvaluationRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
    SourcePollRunRecord,
)
from storage.repository import StorageRepository
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack
from truth.validator import ClaimValidator, opportunity_terms_from_values
from worker.queue import BackgroundWorkerQueue

from .deps import get_db, get_repository, require_session
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


@router.get("/opportunities")
def list_opportunities(
    request: Request,
    track: str | None = None,
    decision: str | None = None,
    min_score: float | None = None,
    since: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
    session: Session = Depends(get_db),
):
    query = session.query(OpportunityRecord)
    if track:
        query = query.filter(OpportunityRecord.track == track)
    if since:
        query = query.filter(OpportunityRecord.created_at >= since)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (OpportunityRecord.title.ilike(like)) | (OpportunityRecord.organization.ilike(like))
        )

    opportunities = query.all()

    rows: list[dict[str, Any]] = []
    for opp in opportunities:
        evaluation = _latest_evaluation(session, opp.id)
        opp_decision = evaluation.qualification_decision if evaluation else None
        fit_score = evaluation.fit_score if evaluation else None

        if decision and opp_decision != decision:
            continue
        if min_score is not None and (fit_score is None or fit_score < min_score):
            continue

        reasons = unpack_reasons(evaluation.reasons_json if evaluation else None)
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
                "top_reasons": top_reasons_from_list(reasons),
                "deadline": opp.deadline,
                "posted_date": opp.posted_date,
                "is_stale": bool(opp.is_stale),
                "action_state": _latest_action_state(session, opp.id),
                "feedback_label": _latest_feedback_label(session, opp.id),
            }
        )

    # fit_score descending, nulls last, then posted_date descending, then id.
    rows.sort(key=lambda r: (r["fit_score"] is None, -(r["fit_score"] or 0), _posted_date_sort_key(r["posted_date"]), r["id"]))

    total = len(rows)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    page_items = rows[start : start + page_size]

    return {"page": page, "page_size": page_size, "total": total, "items": page_items}


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

    validator = ClaimValidator(loaded_pack.graph)
    # Class (b) opportunity-provenanced terms (ADR-0014): derived here, by the
    # caller, from the real Opportunity's own field values -- never guessed
    # inside the validator. Only these two fields carry independent field
    # provenance on the domain Opportunity today (employer name, role title).
    opportunity_terms = opportunity_terms_from_values(domain_opp.organization, domain_opp.title)
    findings: list[dict[str, Any]] = []
    for claim in artifact.generated_claims:
        if claim.policy_source == "NARRATIVE":
            # NARRATIVE segments (ADR-0014) assert no founder-specific fact
            # and cite no evidence; only the prohibited-concept / red-line
            # guards apply, run on the full narrative text.
            result = validator.validate_narrative(claim.text)
        else:
            result = validator.validate_claim(claim.text, claim.evidence_ids, opportunity_terms=opportunity_terms)
        if not result.allowed:
            findings.append(
                {
                    "claim": claim.text,
                    "assertion_type": result.assertion_type.value,
                    "rejection_reasons": list(result.reasons),
                }
            )

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
# Dashboard
# --------------------------------------------------------------------------

@router.get("/dashboard/daily")
def dashboard_daily(request: Request, days: int = 7, session: Session = Depends(get_db)):
    days = max(1, min(days, 90))
    high_fit_threshold = request.app.state.settings.high_fit_threshold
    today = datetime.now(timezone.utc).date()

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
