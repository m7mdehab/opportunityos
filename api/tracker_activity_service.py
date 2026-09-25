"""Bounded read-only activity timeline projection for FR-008."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.models import FounderActivityEventRecord, OpportunityRecord

MAX_PAGE_SIZE = 100


class TrackerActivityError(ValueError):
    """An activity timeline request references a missing opportunity."""


def _iso_utc(value: datetime) -> str:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def list_tracker_activity(
    session: Session,
    opportunity_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return only timeline-safe event scalars, never metadata or idempotency keys."""
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerActivityError("opportunity not found")

    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    base = session.query(FounderActivityEventRecord).filter_by(opportunity_id=opportunity_id)
    total = base.with_entities(func.count(FounderActivityEventRecord.id)).scalar() or 0
    rows = (
        session.query(
            FounderActivityEventRecord.id,
            FounderActivityEventRecord.action_type,
            FounderActivityEventRecord.from_state,
            FounderActivityEventRecord.to_state,
            FounderActivityEventRecord.event_at,
        )
        .filter(FounderActivityEventRecord.opportunity_id == opportunity_id)
        .order_by(FounderActivityEventRecord.event_at.desc(), FounderActivityEventRecord.id.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": [
            {
                "id": event_id,
                "action_type": action_type,
                "from_state": from_state,
                "to_state": to_state,
                "event_at": _iso_utc(event_at),
            }
            for event_id, action_type, from_state, to_state, event_at in rows
        ],
    }
