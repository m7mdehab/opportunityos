"""SQL-backed ID-only application document associations for FR-008."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from matching.cv_selector import PORTFOLIO
from storage.models import (
    ArtifactCacheRecord,
    FounderActivityEventRecord,
    FounderApplicationDetailRecord,
    FounderCVSelectionRecord,
    FounderTrackerDocumentRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)
from api.tracker_service import APPLICATION_STAGES, APPLICATION_TERMINAL_OUTCOMES

MAX_PAGE_SIZE = 100
DOCUMENT_KINDS = frozenset({"cv", "cover_letter"})
APPLICATION_TRACKED_STATES = frozenset((*APPLICATION_STAGES, *APPLICATION_TERMINAL_OUTCOMES))
CV_VARIANT_LABELS = {
    "ai_engineer": "AI Engineer résumé",
    "business_analyst": "Business Analyst résumé",
    "data_analyst": "Data Analyst résumé",
    "data_engineer": "Data Engineer résumé",
    "data_scientist": "Data Scientist résumé",
    "master": "General résumé",
}
CV_VARIANT_IDS = frozenset(item.variant for item in PORTFOLIO)
MAX_COVER_LETTER_CANDIDATES = 100


class TrackerDocumentError(ValueError):
    """An application-document request violates the tracker contract."""


@dataclass(frozen=True)
class DocumentMutation:
    link: dict
    changed: bool


def _idempotency_key(request_key: str | None) -> str:
    if not isinstance(request_key, str) or not request_key.strip():
        raise TrackerDocumentError("idempotency_key is required")
    if len(request_key) > 128:
        raise TrackerDocumentError("idempotency_key is too long")
    digest = hashlib.sha256(f"fr008-tracker-document:{request_key}".encode("utf-8")).hexdigest()
    return f"tracker-document:{digest}"


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _iso_utc(value: datetime | None) -> str | None:
    return _utc_naive(value).isoformat() + "Z" if value is not None else None


def _require_application_state(session: Session, opportunity_id: str) -> str:
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerDocumentError("opportunity not found")
    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state not in APPLICATION_TRACKED_STATES:
        raise TrackerDocumentError("documents are available only for application-tracked jobs")
    return triage.state


def _document_payload(row: FounderTrackerDocumentRecord) -> dict:
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "document_kind": row.document_kind,
        "document_id": row.document_id,
        "linked_at": _iso_utc(row.linked_at),
        "unlinked_at": _iso_utc(row.unlinked_at),
    }


def _document_candidates(
    session: Session,
    opportunity_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    recommended = session.query(FounderCVSelectionRecord.variant).filter_by(opportunity_id=opportunity_id).scalar()
    candidates = [
        {
            "document_kind": "cv",
            "document_id": variant,
            "label": CV_VARIANT_LABELS.get(variant, "Approved résumé"),
            "format": "pdf",
            "recommended": variant == recommended,
        }
        for variant in sorted(CV_VARIANT_IDS)
    ]

    # Select only opaque identity and safe display metadata. ArtifactCacheRecord.payload,
    # object keys, checksums, and storage backend are never hydrated into this query.
    cached_letters = (
        session.query(
            ArtifactCacheRecord.cache_key,
            ArtifactCacheRecord.template_id,
            ArtifactCacheRecord.artifact_kind,
            ArtifactCacheRecord.created_at,
        )
        .filter(
            ArtifactCacheRecord.opportunity_id == opportunity_id,
            ArtifactCacheRecord.artifact_kind.in_(("cover-letter", "cover-letter-pdf")),
        )
        .order_by(ArtifactCacheRecord.created_at.desc(), ArtifactCacheRecord.cache_key.asc())
        .limit(MAX_COVER_LETTER_CANDIDATES)
        .all()
    )
    for cache_key, template_id, artifact_kind, created_at in cached_letters:
        template = template_id if template_id in {"classic", "compact", "modern"} else "saved"
        output_format = "pdf" if artifact_kind == "cover-letter-pdf" else "docx"
        candidates.append({
            "document_kind": "cover_letter",
            "document_id": cache_key,
            "label": f"Cover letter · {template.title()}",
            "format": output_format,
            "recommended": False,
            "created_at": _iso_utc(created_at),
        })

    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = len(candidates)
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": candidates[(normalized_page - 1) * normalized_page_size:normalized_page * normalized_page_size],
    }


def list_tracker_documents(session: Session, opportunity_id: str, *, page: int = 1, page_size: int = 50) -> dict:
    _require_application_state(session, opportunity_id)
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = session.query(FounderTrackerDocumentRecord).filter_by(opportunity_id=opportunity_id, unlinked_at=None)
    total = query.with_entities(func.count(FounderTrackerDocumentRecord.id)).scalar() or 0
    rows = (
        query.order_by(FounderTrackerDocumentRecord.document_kind.asc(), FounderTrackerDocumentRecord.document_id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    details = session.get(FounderApplicationDetailRecord, opportunity_id)
    return {
        "opportunity_id": opportunity_id,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "selected_cv_document_id": details.selected_cv_document_id if details else None,
        "selected_cover_letter_document_id": details.selected_cover_letter_document_id if details else None,
        "items": [_document_payload(row) for row in rows],
    }


def list_tracker_document_candidates(
    session: Session,
    opportunity_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    _require_application_state(session, opportunity_id)
    return _document_candidates(session, opportunity_id, page=page, page_size=page_size)


def _require_candidate(session: Session, opportunity_id: str, document_kind: str, document_id: str) -> None:
    if document_kind not in DOCUMENT_KINDS:
        raise TrackerDocumentError("unknown document_kind")
    if not isinstance(document_id, str) or not document_id.strip() or len(document_id) > 128:
        raise TrackerDocumentError("document_id is required and must be at most 128 characters")
    if document_kind == "cv":
        if document_id not in CV_VARIANT_IDS:
            raise TrackerDocumentError("unknown CV document identity")
        return
    exists = session.query(ArtifactCacheRecord.cache_key).filter(
        ArtifactCacheRecord.cache_key == document_id,
        ArtifactCacheRecord.opportunity_id == opportunity_id,
        ArtifactCacheRecord.artifact_kind.in_(("cover-letter", "cover-letter-pdf")),
    ).first()
    if exists is None:
        raise TrackerDocumentError("cover-letter document identity is unavailable for this opportunity")


def _event_document_identity(event: FounderActivityEventRecord) -> tuple[str | None, str | None]:
    try:
        metadata = json.loads(event.metadata_json)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(metadata, dict):
        return None, None
    kind = metadata.get("document_kind")
    identity = metadata.get("document_id")
    return (kind if isinstance(kind, str) else None, identity if isinstance(identity, str) else None)


def _check_replay(
    session: Session,
    event: FounderActivityEventRecord,
    *,
    opportunity_id: str,
    action_type: str,
    document_kind: str,
    document_id: str,
) -> FounderTrackerDocumentRecord:
    previous_kind, previous_id = _event_document_identity(event)
    if (
        event.opportunity_id != opportunity_id
        or event.action_type != action_type
        or previous_kind != document_kind
        or previous_id != document_id
    ):
        raise TrackerDocumentError("idempotency_key was already used for another document operation")
    row = session.query(FounderTrackerDocumentRecord).filter_by(
        opportunity_id=opportunity_id,
        document_kind=document_kind,
        document_id=document_id,
    ).first()
    if row is None:
        raise TrackerDocumentError("document association not found")
    return row


def _event_for_key(session: Session, key: str) -> FounderActivityEventRecord | None:
    return session.query(FounderActivityEventRecord).filter_by(idempotency_key=key).first()


def _record_event(
    session: Session,
    *,
    opportunity_id: str,
    state: str,
    action_type: str,
    document_kind: str,
    document_id: str,
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
        metadata_json=json.dumps({"document_kind": document_kind, "document_id": document_id}, separators=(",", ":")),
        idempotency_key=idempotency_key,
        created_at=now,
    ))
    session.flush()


def _application_details(session: Session, opportunity_id: str, now: datetime) -> FounderApplicationDetailRecord:
    details = session.get(FounderApplicationDetailRecord, opportunity_id)
    if details is None:
        details = FounderApplicationDetailRecord(opportunity_id=opportunity_id, updated_at=now)
        session.add(details)
        session.flush()
    return details


def link_tracker_document(
    session: Session,
    opportunity_id: str,
    document_kind: str,
    document_id: str,
    now: datetime,
    *,
    request_key: str | None,
) -> DocumentMutation:
    state = _require_application_state(session, opportunity_id)
    _require_candidate(session, opportunity_id, document_kind, document_id)
    key = _idempotency_key(request_key)
    previous = _event_for_key(session, key)
    if previous is not None:
        row = _check_replay(
            session, previous,
            opportunity_id=opportunity_id,
            action_type="tracker_document_linked",
            document_kind=document_kind,
            document_id=document_id,
        )
        return DocumentMutation(_document_payload(row), False)

    timestamp = _utc_naive(now)
    existing = session.query(FounderTrackerDocumentRecord).filter_by(
        opportunity_id=opportunity_id,
        document_kind=document_kind,
        document_id=document_id,
    ).first()
    active = session.query(FounderTrackerDocumentRecord).filter_by(
        opportunity_id=opportunity_id,
        document_kind=document_kind,
        unlinked_at=None,
    ).all()
    if existing is not None and existing.unlinked_at is None and len(active) == 1:
        return DocumentMutation(_document_payload(existing), False)

    for old_link in active:
        if old_link.document_id != document_id:
            old_link.unlinked_at = timestamp
    if existing is None:
        existing = FounderTrackerDocumentRecord(
            id=f"tracker-document-{uuid.uuid4().hex}",
            opportunity_id=opportunity_id,
            document_kind=document_kind,
            document_id=document_id,
            content_sha256=None,
            linked_at=timestamp,
            unlinked_at=None,
        )
        session.add(existing)
    else:
        existing.linked_at = timestamp
        existing.unlinked_at = None

    details = _application_details(session, opportunity_id, timestamp)
    if document_kind == "cv":
        details.selected_cv_document_id = document_id
    else:
        details.selected_cover_letter_document_id = document_id
    details.updated_at = timestamp
    session.flush()
    _record_event(
        session,
        opportunity_id=opportunity_id,
        state=state,
        action_type="tracker_document_linked",
        document_kind=document_kind,
        document_id=document_id,
        now=timestamp,
        idempotency_key=key,
    )
    return DocumentMutation(_document_payload(existing), True)


def unlink_tracker_document(
    session: Session,
    opportunity_id: str,
    link_id: str,
    now: datetime,
    *,
    request_key: str | None,
) -> DocumentMutation:
    state = _require_application_state(session, opportunity_id)
    row = session.query(FounderTrackerDocumentRecord).filter_by(id=link_id, opportunity_id=opportunity_id).first()
    if row is None:
        raise TrackerDocumentError("document association not found")
    key = _idempotency_key(request_key)
    previous = _event_for_key(session, key)
    if previous is not None:
        replay = _check_replay(
            session, previous,
            opportunity_id=opportunity_id,
            action_type="tracker_document_unlinked",
            document_kind=row.document_kind,
            document_id=row.document_id,
        )
        return DocumentMutation(_document_payload(replay), False)
    if row.unlinked_at is not None:
        return DocumentMutation(_document_payload(row), False)

    timestamp = _utc_naive(now)
    row.unlinked_at = timestamp
    details = _application_details(session, opportunity_id, timestamp)
    if row.document_kind == "cv" and details.selected_cv_document_id == row.document_id:
        details.selected_cv_document_id = None
        details.updated_at = timestamp
    elif row.document_kind == "cover_letter" and details.selected_cover_letter_document_id == row.document_id:
        details.selected_cover_letter_document_id = None
        details.updated_at = timestamp
    session.flush()
    _record_event(
        session,
        opportunity_id=opportunity_id,
        state=state,
        action_type="tracker_document_unlinked",
        document_kind=row.document_kind,
        document_id=row.document_id,
        now=timestamp,
        idempotency_key=key,
    )
    return DocumentMutation(_document_payload(row), True)
