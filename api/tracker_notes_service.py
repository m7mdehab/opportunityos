"""SQL-backed operations for private FR-008 tracker notes."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.tracker_service import APPLICATION_STAGES, APPLICATION_TERMINAL_OUTCOMES
from storage.models import (
    FounderActivityEventRecord,
    FounderTrackerNoteRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)

MAX_NOTE_LENGTH = 4_000
MAX_PAGE_SIZE = 100
APPLICATION_TRACKED_STATES = frozenset((*APPLICATION_STAGES, *APPLICATION_TERMINAL_OUTCOMES))


class TrackerNoteError(ValueError):
    """A tracker-note request violates the private notes contract."""


@dataclass(frozen=True)
class TrackerNoteMutation:
    note: dict
    changed: bool


def _idempotency_key(opportunity_id: str, request_key: str | None) -> str:
    if not isinstance(request_key, str) or not request_key.strip():
        raise TrackerNoteError("idempotency_key is required")
    if len(request_key) > 128:
        raise TrackerNoteError("idempotency_key is too long")
    digest = hashlib.sha256(
        f"fr008-tracker-note:{opportunity_id}:{request_key}".encode("utf-8")
    ).hexdigest()
    return f"tracker-note:{digest}"


def _clean_note_text(note_text: str | None) -> str:
    if not isinstance(note_text, str):
        raise TrackerNoteError("note_text is required")
    cleaned = note_text.strip()
    if not cleaned:
        raise TrackerNoteError("note_text cannot be blank")
    if len(cleaned) > MAX_NOTE_LENGTH:
        raise TrackerNoteError(f"note_text cannot exceed {MAX_NOTE_LENGTH} characters")
    return cleaned


def _require_application_tracker_item(session: Session, opportunity_id: str) -> str:
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerNoteError("opportunity not found")
    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state not in APPLICATION_TRACKED_STATES:
        raise TrackerNoteError("opportunity is not an application-tracked item")
    return triage.state


def _note_payload(note: FounderTrackerNoteRecord) -> dict:
    return {
        "id": note.id,
        "opportunity_id": note.opportunity_id,
        "note_text": note.note_text,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
        "archived_at": note.archived_at.isoformat() if note.archived_at else None,
    }


def _event_for_key(session: Session, key: str) -> FounderActivityEventRecord | None:
    return session.query(FounderActivityEventRecord).filter_by(idempotency_key=key).first()


def _event_note_id(event: FounderActivityEventRecord) -> str | None:
    try:
        metadata = json.loads(event.metadata_json)
    except (TypeError, ValueError):
        return None
    note_id = metadata.get("note_id") if isinstance(metadata, dict) else None
    return note_id if isinstance(note_id, str) else None


def _raise_if_key_reused_for_other_operation(
    event: FounderActivityEventRecord,
    *,
    action_type: str,
    note_id: str | None,
) -> str:
    prior_note_id = _event_note_id(event)
    if event.action_type != action_type or (note_id is not None and prior_note_id != note_id):
        raise TrackerNoteError("idempotency_key was already used for another note operation")
    if prior_note_id is None:
        raise TrackerNoteError("idempotency record is missing its note reference")
    return prior_note_id


def list_tracker_notes(
    session: Session,
    opportunity_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    _require_application_tracker_item(session, opportunity_id)
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = session.query(FounderTrackerNoteRecord).filter_by(
        opportunity_id=opportunity_id,
        archived_at=None,
    )
    total = query.with_entities(func.count(FounderTrackerNoteRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderTrackerNoteRecord.created_at.desc(), FounderTrackerNoteRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": [_note_payload(note) for note in rows],
    }


def create_tracker_note(
    session: Session,
    opportunity_id: str,
    note_text: str,
    now: datetime,
    *,
    request_key: str | None,
) -> TrackerNoteMutation:
    state = _require_application_tracker_item(session, opportunity_id)
    cleaned = _clean_note_text(note_text)
    key = _idempotency_key(opportunity_id, request_key)
    previous_event = _event_for_key(session, key)
    if previous_event is not None:
        note_id = _raise_if_key_reused_for_other_operation(
            previous_event,
            action_type="tracker_note_created",
            note_id=None,
        )
        note = session.query(FounderTrackerNoteRecord).filter_by(
            id=note_id,
            opportunity_id=opportunity_id,
        ).first()
        if note is None:
            raise TrackerNoteError("note not found")
        return TrackerNoteMutation(_note_payload(note), False)

    note = FounderTrackerNoteRecord(
        id=f"tracker-note-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        note_text=cleaned,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )
    session.add(note)
    session.flush()
    session.add(FounderActivityEventRecord(
        id=f"tracker-event-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        action_type="tracker_note_created",
        from_state=state,
        to_state=state,
        event_at=now,
        metadata_json=json.dumps({"note_id": note.id}, separators=(",", ":")),
        idempotency_key=key,
        created_at=now,
    ))
    session.flush()
    return TrackerNoteMutation(_note_payload(note), True)


def update_tracker_note(
    session: Session,
    opportunity_id: str,
    note_id: str,
    now: datetime,
    *,
    request_key: str | None,
    note_text: str | None = None,
    archive: bool = False,
) -> TrackerNoteMutation:
    state = _require_application_tracker_item(session, opportunity_id)
    if (note_text is None and not archive) or (note_text is not None and archive):
        raise TrackerNoteError("provide note_text or archived=true")
    cleaned = _clean_note_text(note_text) if note_text is not None else None
    key = _idempotency_key(opportunity_id, request_key)
    note = session.query(FounderTrackerNoteRecord).filter_by(
        id=note_id,
        opportunity_id=opportunity_id,
    ).first()
    if note is None:
        raise TrackerNoteError("note not found")

    action_type = "tracker_note_archived" if archive else "tracker_note_updated"
    previous_event = _event_for_key(session, key)
    if previous_event is not None:
        _raise_if_key_reused_for_other_operation(
            previous_event,
            action_type=action_type,
            note_id=note_id,
        )
        return TrackerNoteMutation(_note_payload(note), False)

    if archive:
        if note.archived_at is not None:
            return TrackerNoteMutation(_note_payload(note), False)
        note.archived_at = now
    else:
        if note.archived_at is not None:
            raise TrackerNoteError("archived notes cannot be edited")
        if note.note_text == cleaned:
            return TrackerNoteMutation(_note_payload(note), False)
        note.note_text = cleaned
    note.updated_at = now
    session.add(FounderActivityEventRecord(
        id=f"tracker-event-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        action_type=action_type,
        from_state=state,
        to_state=state,
        event_at=now,
        metadata_json=json.dumps({"note_id": note.id}, separators=(",", ":")),
        idempotency_key=key,
        created_at=now,
    ))
    session.flush()
    return TrackerNoteMutation(_note_payload(note), True)
