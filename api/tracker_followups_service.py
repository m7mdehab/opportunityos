"""SQL-backed operations for private FR-008 tracker follow-ups."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.tracker_service import BUCKET_STATES
from storage.models import (
    FounderActivityEventRecord,
    FounderFollowUpRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)

MAX_NOTE_LENGTH = 4_000
MAX_PAGE_SIZE = 100
FOLLOW_UP_STATES = frozenset((*BUCKET_STATES["saved"], *BUCKET_STATES["applied"]))
FOLLOW_UP_BUCKETS = frozenset({"due_today", "overdue", "upcoming"})


class TrackerFollowUpError(ValueError):
    """A follow-up request violates the private tracker contract."""


@dataclass(frozen=True)
class FollowUpMutation:
    follow_up: dict
    changed: bool


def _idempotency_key(request_key: str | None) -> str:
    if not isinstance(request_key, str) or not request_key.strip():
        raise TrackerFollowUpError("idempotency_key is required")
    if len(request_key) > 128:
        raise TrackerFollowUpError("idempotency_key is too long")
    digest = hashlib.sha256(
        f"fr008-tracker-follow-up:{request_key}".encode("utf-8")
    ).hexdigest()
    return f"tracker-follow-up:{digest}"


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_date(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(timezone.utc).date()


def _parse_due_date(value: str | None) -> tuple[date, datetime]:
    if not isinstance(value, str):
        raise TrackerFollowUpError("due_date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TrackerFollowUpError("due_date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise TrackerFollowUpError("due_date must use YYYY-MM-DD")
    return parsed, datetime.combine(parsed, time.min)


def _clean_optional_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrackerFollowUpError("note_text must be a string or null")
    cleaned = value.strip()
    if len(cleaned) > MAX_NOTE_LENGTH:
        raise TrackerFollowUpError(f"note_text cannot exceed {MAX_NOTE_LENGTH} characters")
    return cleaned or None


def _require_follow_up_state(session: Session, opportunity_id: str) -> str:
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerFollowUpError("opportunity not found")
    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state not in FOLLOW_UP_STATES:
        raise TrackerFollowUpError("follow-ups are available only for Saved and Applied jobs")
    return triage.state


def _status(due_on: date, completed_at: datetime | None, today: date) -> str:
    if completed_at is not None:
        return "completed"
    if due_on < today:
        return "overdue"
    if due_on == today:
        return "due_today"
    return "upcoming"


def _follow_up_payload(
    follow_up: FounderFollowUpRecord,
    *,
    today: date,
    include_note: bool = True,
) -> dict:
    due_on = follow_up.due_at.date()
    payload = {
        "id": follow_up.id,
        "opportunity_id": follow_up.opportunity_id,
        "due_date": due_on.isoformat(),
        "completed_at": follow_up.completed_at.isoformat() if follow_up.completed_at else None,
        "status": _status(due_on, follow_up.completed_at, today),
        "created_at": follow_up.created_at.isoformat(),
        "updated_at": follow_up.updated_at.isoformat(),
    }
    if include_note:
        payload["note_text"] = follow_up.note_text
    return payload


def _event_for_key(session: Session, key: str) -> FounderActivityEventRecord | None:
    return session.query(FounderActivityEventRecord).filter_by(idempotency_key=key).first()


def _event_follow_up_id(event: FounderActivityEventRecord) -> str | None:
    try:
        metadata = json.loads(event.metadata_json)
    except (TypeError, ValueError):
        return None
    follow_up_id = metadata.get("follow_up_id") if isinstance(metadata, dict) else None
    return follow_up_id if isinstance(follow_up_id, str) else None


def _check_replay(
    session: Session,
    event: FounderActivityEventRecord,
    *,
    opportunity_id: str,
    action_type: str,
    follow_up_id: str | None,
) -> FounderFollowUpRecord:
    previous_id = _event_follow_up_id(event)
    if (
        event.opportunity_id != opportunity_id
        or event.action_type != action_type
        or (follow_up_id is not None and previous_id != follow_up_id)
        or previous_id is None
    ):
        raise TrackerFollowUpError("idempotency_key was already used for another follow-up operation")
    row = session.query(FounderFollowUpRecord).filter_by(
        id=previous_id,
        opportunity_id=opportunity_id,
    ).first()
    if row is None:
        raise TrackerFollowUpError("follow-up not found")
    return row


def _add_event(
    session: Session,
    *,
    opportunity_id: str,
    state: str,
    action_type: str,
    follow_up_id: str,
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
        metadata_json=json.dumps({"follow_up_id": follow_up_id}, separators=(",", ":")),
        idempotency_key=idempotency_key,
        created_at=now,
    ))
    session.flush()


def list_tracker_follow_ups(
    session: Session,
    bucket: str,
    *,
    today: date,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    if bucket not in FOLLOW_UP_BUCKETS:
        raise TrackerFollowUpError("unknown follow-up bucket")
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = (
        session.query(FounderFollowUpRecord, FounderTriageStateRecord, OpportunityRecord)
        .join(FounderTriageStateRecord, FounderTriageStateRecord.opportunity_id == FounderFollowUpRecord.opportunity_id)
        .join(OpportunityRecord, OpportunityRecord.id == FounderFollowUpRecord.opportunity_id)
        .filter(
            FounderTriageStateRecord.state.in_(FOLLOW_UP_STATES),
            FounderFollowUpRecord.completed_at.is_(None),
        )
    )
    today_start = datetime.combine(today, time.min)
    next_day = datetime.combine(date.fromordinal(today.toordinal() + 1), time.min)
    if bucket == "overdue":
        query = query.filter(FounderFollowUpRecord.due_at < today_start)
    elif bucket == "due_today":
        query = query.filter(
            FounderFollowUpRecord.due_at >= today_start,
            FounderFollowUpRecord.due_at < next_day,
        )
    else:
        query = query.filter(FounderFollowUpRecord.due_at >= next_day)
    total = query.with_entities(func.count(FounderFollowUpRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderFollowUpRecord.due_at.asc(), FounderFollowUpRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    items = []
    for follow_up, triage, opportunity in rows:
        items.append({
            **_follow_up_payload(follow_up, today=today, include_note=False),
            "opportunity": {
                "id": opportunity.id,
                "title": opportunity.title,
                "organization": opportunity.organization,
                "tracker_state": triage.state,
            },
        })
    return {
        "bucket": bucket,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": items,
    }


def list_opportunity_follow_ups(
    session: Session,
    opportunity_id: str,
    *,
    today: date,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    _require_follow_up_state(session, opportunity_id)
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = session.query(FounderFollowUpRecord).filter_by(opportunity_id=opportunity_id)
    total = query.with_entities(func.count(FounderFollowUpRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderFollowUpRecord.due_at.asc(), FounderFollowUpRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": [_follow_up_payload(row, today=today) for row in rows],
    }


def create_tracker_follow_up(
    session: Session,
    opportunity_id: str,
    due_date: str,
    note_text: str | None,
    now: datetime,
    *,
    request_key: str | None,
) -> FollowUpMutation:
    state = _require_follow_up_state(session, opportunity_id)
    due_on, due_at = _parse_due_date(due_date)
    cleaned_note = _clean_optional_note(note_text)
    key = _idempotency_key(request_key)
    previous_event = _event_for_key(session, key)
    if previous_event is not None:
        row = _check_replay(
            session,
            previous_event,
            opportunity_id=opportunity_id,
            action_type="follow_up_created",
            follow_up_id=None,
        )
        return FollowUpMutation(_follow_up_payload(row, today=_utc_date(now)), False)

    timestamp = _utc_naive(now)
    follow_up = FounderFollowUpRecord(
        id=f"tracker-follow-up-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        due_at=due_at,
        completed_at=None,
        note_text=cleaned_note,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(follow_up)
    session.flush()
    _add_event(
        session,
        opportunity_id=opportunity_id,
        state=state,
        action_type="follow_up_created",
        follow_up_id=follow_up.id,
        now=timestamp,
        idempotency_key=key,
    )
    return FollowUpMutation(_follow_up_payload(follow_up, today=_utc_date(now)), True)


def update_tracker_follow_up(
    session: Session,
    opportunity_id: str,
    follow_up_id: str,
    now: datetime,
    *,
    request_key: str | None,
    due_date: str | None = None,
    note_text: str | None = None,
    note_text_provided: bool = False,
    completed: bool | None = None,
) -> FollowUpMutation:
    state = _require_follow_up_state(session, opportunity_id)
    if completed is not None and (due_date is not None or note_text_provided):
        raise TrackerFollowUpError("provide completion state or due_date/note_text changes, not both")
    if completed is None and due_date is None and not note_text_provided:
        raise TrackerFollowUpError("provide due_date, note_text, or completed")
    parsed_due: tuple[date, datetime] | None = _parse_due_date(due_date) if due_date is not None else None
    cleaned_note = _clean_optional_note(note_text) if note_text_provided else None
    timestamp = _utc_naive(now)
    follow_up = session.query(FounderFollowUpRecord).filter_by(
        id=follow_up_id,
        opportunity_id=opportunity_id,
    ).first()
    if follow_up is None:
        raise TrackerFollowUpError("follow-up not found")

    if completed is True:
        action_type = "follow_up_completed"
    elif completed is False:
        action_type = "follow_up_reopened"
    else:
        action_type = "follow_up_updated"
    key = _idempotency_key(request_key)
    previous_event = _event_for_key(session, key)
    if previous_event is not None:
        row = _check_replay(
            session,
            previous_event,
            opportunity_id=opportunity_id,
            action_type=action_type,
            follow_up_id=follow_up_id,
        )
        return FollowUpMutation(_follow_up_payload(row, today=_utc_date(now)), False)

    changed = False
    if completed is not None:
        if completed and follow_up.completed_at is None:
            follow_up.completed_at = timestamp
            changed = True
        elif not completed and follow_up.completed_at is not None:
            follow_up.completed_at = None
            changed = True
    else:
        if parsed_due is not None and follow_up.due_at != parsed_due[1]:
            follow_up.due_at = parsed_due[1]
            changed = True
        if note_text_provided and follow_up.note_text != cleaned_note:
            follow_up.note_text = cleaned_note
            changed = True
    if not changed:
        return FollowUpMutation(_follow_up_payload(follow_up, today=_utc_date(now)), False)

    follow_up.updated_at = timestamp
    _add_event(
        session,
        opportunity_id=opportunity_id,
        state=state,
        action_type=action_type,
        follow_up_id=follow_up.id,
        now=timestamp,
        idempotency_key=key,
    )
    return FollowUpMutation(_follow_up_payload(follow_up, today=_utc_date(now)), True)
