"""SQL-backed operations for private FR-008 tracker interviews."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.tracker_service import BUCKET_STATES
from storage.models import (
    FounderActivityEventRecord,
    FounderInterviewRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)

MAX_PAGE_SIZE = 100
MAX_LENGTHS = {
    "round_label": 64,
    "interviewer_name": 128,
    "preparation_notes": 4_000,
    "post_interview_notes": 4_000,
}
INTERVIEW_TYPES = frozenset({
    "recruiter_screen", "hiring_manager", "technical", "take_home", "live_coding",
    "case_study", "panel", "final", "other",
})
INTERVIEW_FORMATS = frozenset({"phone", "video", "in_person"})
INTERVIEW_OUTCOMES = frozenset({"pending", "completed", "passed", "not_selected", "cancelled", "other"})
UPCOMING_EXCLUDED_OUTCOMES = frozenset({"completed", "passed", "not_selected", "cancelled"})
APPLICATION_STATES = frozenset(BUCKET_STATES["applied"])
MUTABLE_FIELDS = tuple(MAX_LENGTHS) + ("scheduled_at", "interview_type", "interview_format", "outcome")


class TrackerInterviewError(ValueError):
    """An interview request violates the private tracker contract."""


@dataclass(frozen=True)
class InterviewMutation:
    interview: dict
    changed: bool


def _idempotency_key(opportunity_id: str, request_key: str | None) -> str:
    if not isinstance(request_key, str) or not request_key.strip():
        raise TrackerInterviewError("idempotency_key is required")
    if len(request_key) > 128:
        raise TrackerInterviewError("idempotency_key is too long")
    digest = hashlib.sha256(
        f"fr008-tracker-interview:{request_key}".encode("utf-8")
    ).hexdigest()
    return f"tracker-interview:{digest}"


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc_naive(value).isoformat() + "Z"


def _parse_scheduled_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrackerInterviewError("scheduled_at must be an ISO 8601 datetime with an offset or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrackerInterviewError("scheduled_at must be an ISO 8601 datetime with an offset or null") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrackerInterviewError("scheduled_at must include an explicit UTC offset")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _clean_optional_text(field: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrackerInterviewError(f"{field} must be a string or null")
    cleaned = value.strip()
    if len(cleaned) > MAX_LENGTHS[field]:
        raise TrackerInterviewError(f"{field} cannot exceed {MAX_LENGTHS[field]} characters")
    return cleaned or None


def _validate_enum(field: str, value: str | None, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise TrackerInterviewError(f"unknown {field}")
    return value


def _require_application_state(session: Session, opportunity_id: str) -> str:
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerInterviewError("opportunity not found")
    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state not in APPLICATION_STATES:
        raise TrackerInterviewError("interviews are available only for Applied jobs")
    return triage.state


def _payload(row: FounderInterviewRecord, *, include_notes: bool = True) -> dict:
    result = {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "scheduled_at": _iso_utc(row.scheduled_at),
        "round_label": row.round_label,
        "interview_type": row.interview_type,
        "interview_format": row.interview_format,
        "interviewer_name": row.interviewer_name,
        "outcome": row.outcome,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }
    if include_notes:
        result["preparation_notes"] = row.preparation_notes
        result["post_interview_notes"] = row.post_interview_notes
    return result


def _event_for_key(session: Session, key: str) -> FounderActivityEventRecord | None:
    return session.query(FounderActivityEventRecord).filter_by(idempotency_key=key).first()


def _event_interview_id(event: FounderActivityEventRecord) -> str | None:
    try:
        metadata = json.loads(event.metadata_json)
    except (TypeError, ValueError):
        return None
    value = metadata.get("interview_id") if isinstance(metadata, dict) else None
    return value if isinstance(value, str) else None


def _check_replay(
    session: Session,
    event: FounderActivityEventRecord,
    *,
    opportunity_id: str,
    action_type: str,
    interview_id: str | None,
) -> FounderInterviewRecord:
    previous_id = _event_interview_id(event)
    if (
        event.opportunity_id != opportunity_id
        or event.action_type != action_type
        or (interview_id is not None and previous_id != interview_id)
        or previous_id is None
    ):
        raise TrackerInterviewError("idempotency_key was already used for another interview operation")
    row = session.query(FounderInterviewRecord).filter_by(id=previous_id, opportunity_id=opportunity_id).first()
    if row is None:
        raise TrackerInterviewError("interview not found")
    return row


def _add_event(
    session: Session,
    *,
    opportunity_id: str,
    state: str,
    action_type: str,
    interview_id: str,
    now: datetime,
    idempotency_key: str,
) -> None:
    session.add(FounderActivityEventRecord(
        id=f"tracker-event-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        action_type=action_type,
        from_state=state,
        to_state=state,
        event_at=now,
        metadata_json=json.dumps({"interview_id": interview_id}, separators=(",", ":")),
        idempotency_key=idempotency_key,
        created_at=now,
    ))
    session.flush()


def list_opportunity_interviews(
    session: Session,
    opportunity_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    _require_application_state(session, opportunity_id)
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = session.query(FounderInterviewRecord).filter_by(opportunity_id=opportunity_id)
    total = query.with_entities(func.count(FounderInterviewRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderInterviewRecord.scheduled_at.asc().nullslast(), FounderInterviewRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": [_payload(row) for row in rows],
    }


def list_tracker_interviews(
    session: Session,
    bucket: str,
    *,
    now: datetime,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    if bucket != "upcoming":
        raise TrackerInterviewError("unknown interview bucket")
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    timestamp = _utc_naive(now)
    query = (
        session.query(FounderInterviewRecord, FounderTriageStateRecord, OpportunityRecord)
        .join(FounderTriageStateRecord, FounderTriageStateRecord.opportunity_id == FounderInterviewRecord.opportunity_id)
        .join(OpportunityRecord, OpportunityRecord.id == FounderInterviewRecord.opportunity_id)
        .filter(
            FounderTriageStateRecord.state.in_(APPLICATION_STATES),
            FounderInterviewRecord.scheduled_at.is_not(None),
            FounderInterviewRecord.scheduled_at >= timestamp,
        )
        .filter(
            (FounderInterviewRecord.outcome.is_(None))
            | (~FounderInterviewRecord.outcome.in_(UPCOMING_EXCLUDED_OUTCOMES))
        )
    )
    total = query.with_entities(func.count(FounderInterviewRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderInterviewRecord.scheduled_at.asc(), FounderInterviewRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    items = []
    for interview, triage, opportunity in rows:
        items.append({
            **_payload(interview, include_notes=False),
            "opportunity": {
                "id": opportunity.id,
                "title": opportunity.title,
                "organization": opportunity.organization,
                "tracker_state": triage.state,
            },
        })
    return {"bucket": bucket, "page": normalized_page, "page_size": normalized_page_size, "total": total, "items": items}


def create_tracker_interview(
    session: Session,
    opportunity_id: str,
    fields: dict,
    now: datetime,
    *,
    request_key: str | None,
) -> InterviewMutation:
    state = _require_application_state(session, opportunity_id)
    normalized = _normalize_fields(fields)
    key = _idempotency_key(opportunity_id, request_key)
    previous = _event_for_key(session, key)
    if previous is not None:
        row = _check_replay(session, previous, opportunity_id=opportunity_id, action_type="interview_added", interview_id=None)
        return InterviewMutation(_payload(row), False)
    timestamp = _utc_naive(now)
    row = FounderInterviewRecord(
        id=f"tracker-interview-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        scheduled_at=normalized.get("scheduled_at"),
        round_label=normalized.get("round_label"),
        interview_type=normalized.get("interview_type"),
        interview_format=normalized.get("interview_format"),
        interviewer_name=normalized.get("interviewer_name"),
        preparation_notes=normalized.get("preparation_notes"),
        post_interview_notes=normalized.get("post_interview_notes"),
        outcome=normalized.get("outcome") or "pending",
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(row)
    session.flush()
    _add_event(session, opportunity_id=opportunity_id, state=state, action_type="interview_added", interview_id=row.id, now=timestamp, idempotency_key=key)
    return InterviewMutation(_payload(row), True)


def _normalize_fields(fields: dict, *, allow_partial: bool = False) -> dict:
    normalized: dict = {}
    for field, value in fields.items():
        if field not in MUTABLE_FIELDS:
            raise TrackerInterviewError(f"unknown interview field: {field}")
        if field == "scheduled_at":
            normalized[field] = _parse_scheduled_at(value)
        elif field in MAX_LENGTHS:
            normalized[field] = _clean_optional_text(field, value)
        elif field == "interview_type":
            normalized[field] = _validate_enum(field, value, INTERVIEW_TYPES)
        elif field == "interview_format":
            normalized[field] = _validate_enum(field, value, INTERVIEW_FORMATS)
        elif field == "outcome":
            normalized[field] = _validate_enum(field, value, INTERVIEW_OUTCOMES)
    return normalized


def update_tracker_interview(
    session: Session,
    opportunity_id: str,
    interview_id: str,
    fields: dict,
    now: datetime,
    *,
    request_key: str | None,
) -> InterviewMutation:
    state = _require_application_state(session, opportunity_id)
    if not fields:
        raise TrackerInterviewError("provide at least one interview field")
    normalized = _normalize_fields(fields, allow_partial=True)
    row = session.query(FounderInterviewRecord).filter_by(id=interview_id, opportunity_id=opportunity_id).first()
    if row is None:
        raise TrackerInterviewError("interview not found")
    old_outcome = row.outcome
    next_outcome = normalized.get("outcome", old_outcome)
    is_completion_transition = old_outcome in (None, "pending") and next_outcome in {"completed", "passed", "not_selected"}
    is_completion_replay = (
        set(normalized) == {"outcome"}
        and old_outcome in {"completed", "passed", "not_selected"}
        and next_outcome == old_outcome
    )
    if is_completion_transition or is_completion_replay:
        action_type = "interview_completed"
    else:
        action_type = "interview_updated"
    key = _idempotency_key(opportunity_id, request_key)
    previous = _event_for_key(session, key)
    if previous is not None:
        replay = _check_replay(session, previous, opportunity_id=opportunity_id, action_type=action_type, interview_id=interview_id)
        return InterviewMutation(_payload(replay), False)
    if all(getattr(row, field) == value for field, value in normalized.items()):
        return InterviewMutation(_payload(row), False)
    timestamp = _utc_naive(now)
    for field, value in normalized.items():
        setattr(row, field, value)
    row.updated_at = timestamp
    session.flush()
    _add_event(session, opportunity_id=opportunity_id, state=state, action_type=action_type, interview_id=row.id, now=timestamp, idempotency_key=key)
    return InterviewMutation(_payload(row), True)
