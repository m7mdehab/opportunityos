"""C1 (BRIEF-FR-006) -- saved views: named facet sets (+ search query) the
founder can create, read, update, delete, and mark as the default. Persisted
in `founder_saved_views` (migration `0004_founder_control`, work order A1M).

A saved view stores an opaque `facets` JSON object (the shape
`api/routes_api.py`'s facet PUT bodies already use: `{facet_id: {"include":
[...], "exclude": [...]}}`) plus a free-text `search_query` string (the C2
search seam -- this module never parses or validates the query itself, C2
owns that). Round-trip fidelity through the database, including across a
fresh session (a process restart), is the whole point of this table; nothing
here caches a Python object across requests.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from storage.models import FounderSavedViewRecord


def serialize_saved_view(row: FounderSavedViewRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "facets": json.loads(row.facets_json) if row.facets_json else {},
        "search_query": row.search_query,
        "is_default": bool(row.is_default),
    }


def list_saved_views(session: Session) -> list[dict[str, Any]]:
    rows = session.query(FounderSavedViewRecord).order_by(FounderSavedViewRecord.name.asc()).all()
    return [serialize_saved_view(row) for row in rows]


def get_saved_view(session: Session, view_id: str) -> dict[str, Any] | None:
    row = session.query(FounderSavedViewRecord).filter_by(id=view_id).first()
    return serialize_saved_view(row) if row is not None else None


def get_default_saved_view(session: Session) -> dict[str, Any] | None:
    row = session.query(FounderSavedViewRecord).filter_by(is_default=True).first()
    return serialize_saved_view(row) if row is not None else None


def create_saved_view(
    session: Session,
    *,
    name: str,
    facets: dict[str, Any],
    search_query: str | None,
    is_default: bool,
    now: datetime,
    view_id: str | None = None,
) -> dict[str, Any]:
    if is_default:
        # Exactly one default at a time: demote any existing default before
        # this row (potentially) claims it.
        session.query(FounderSavedViewRecord).update({FounderSavedViewRecord.is_default: False})
    row = FounderSavedViewRecord(
        id=view_id or f"view-{uuid.uuid4().hex[:16]}",
        name=name,
        facets_json=json.dumps(facets),
        search_query=search_query,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return serialize_saved_view(row)


def update_saved_view(
    session: Session,
    view_id: str,
    *,
    name: str | None = None,
    facets: dict[str, Any] | None = None,
    search_query: str | None = None,
    is_default: bool | None = None,
    now: datetime,
) -> dict[str, Any] | None:
    row = session.query(FounderSavedViewRecord).filter_by(id=view_id).first()
    if row is None:
        return None
    if name is not None:
        row.name = name
    if facets is not None:
        row.facets_json = json.dumps(facets)
    if search_query is not None:
        row.search_query = search_query
    if is_default is not None:
        if is_default:
            session.query(FounderSavedViewRecord).filter(FounderSavedViewRecord.id != view_id).update(
                {FounderSavedViewRecord.is_default: False}
            )
        row.is_default = is_default
    row.updated_at = now
    session.commit()
    return serialize_saved_view(row)


def delete_saved_view(session: Session, view_id: str) -> bool:
    row = session.query(FounderSavedViewRecord).filter_by(id=view_id).first()
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
