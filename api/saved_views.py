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

_SAVED_VIEW_ENVELOPE = "__opportunityos_saved_view_v2"


def _unpack_facets_payload(raw: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(raw, dict):
        return {}, None
    envelope = raw.get(_SAVED_VIEW_ENVELOPE)
    if (
        isinstance(envelope, dict)
        and envelope.get("version") == 2
        and isinstance(raw.get("facet_selections"), dict)
    ):
        feed_query = raw.get("feed_query")
        return (
            raw["facet_selections"],
            feed_query if isinstance(feed_query, dict) else None,
        )
    return raw, None


def _pack_facets_payload(
    facets: dict[str, Any], feed_query: dict[str, Any] | None
) -> str:
    if feed_query is None:
        # Keep legacy C1 payloads byte-shape compatible for older clients.
        payload: dict[str, Any] = facets
    else:
        payload = {
            _SAVED_VIEW_ENVELOPE: {"version": 2},
            "facet_selections": facets,
            "feed_query": feed_query,
        }
    return json.dumps(payload)


def serialize_saved_view(row: FounderSavedViewRecord) -> dict[str, Any]:
    facets, feed_query = _unpack_facets_payload(
        json.loads(row.facets_json) if row.facets_json else {}
    )
    return {
        "id": row.id,
        "name": row.name,
        "facets": facets,
        "search_query": row.search_query,
        "feed_query": feed_query,
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
    feed_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if is_default:
        # Exactly one default at a time: demote any existing default before
        # this row (potentially) claims it.
        session.query(FounderSavedViewRecord).update({FounderSavedViewRecord.is_default: False})
    row = FounderSavedViewRecord(
        id=view_id or f"view-{uuid.uuid4().hex[:16]}",
        name=name,
        facets_json=_pack_facets_payload(facets, feed_query),
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
    feed_query: dict[str, Any] | None = None,
    search_query: str | None = None,
    is_default: bool | None = None,
    now: datetime,
) -> dict[str, Any] | None:
    row = session.query(FounderSavedViewRecord).filter_by(id=view_id).first()
    if row is None:
        return None
    if name is not None:
        row.name = name
    if facets is not None or feed_query is not None:
        current_facets, current_query = _unpack_facets_payload(
            json.loads(row.facets_json) if row.facets_json else {}
        )
        row.facets_json = _pack_facets_payload(
            facets if facets is not None else current_facets,
            feed_query if feed_query is not None else current_query,
        )
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
