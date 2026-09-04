"""Artifact generation cache (BRIEF-FR-006 D2), keyed on
`(opportunity_id, truth_pack_hash, template_id, artifact_kind)` per the
brief's D2 deliverable text. The `artifact_cache` table already exists
(migration `0004_founder_control`, work order A1; see
`storage/models.py::ArtifactCacheRecord`) -- this module only reads and
writes rows in it. No migration is added here.

Table columns have no separate "format" column, so PDF and DOCX
generations for the same opportunity/kind/template are kept apart by
folding the format into `artifact_kind` (see `pdf_kind`/`docx_kind` in
`api/routes_api.py`): e.g. `"cv"` for the DOCX and `"cv-pdf"` for the PDF.

Eviction / size policy (BRIEF-FR-006 D2 requirement: "eviction or size
bounds are stated, whatever you choose"):

1. **Hash-keyed invalidation.** `truth_pack_hash` is part of the cache
   key, so editing the founder's truth pack never serves a stale
   document -- it simply misses under a new key. `store()` prunes any
   *other* rows already on file for the same
   `(opportunity_id, artifact_kind, template_id)` whose
   `truth_pack_hash` differs from the one just generated, so at most one
   row survives per (opportunity, kind, template) triple at any time --
   the table does not grow with truth-pack edit history.
2. **Global row cap.** `store()` also caps the table at `MAX_CACHE_ROWS`
   total rows, deleting the oldest rows (by `created_at`) beyond the cap
   after every insert. This is a simple, predictable LRU-by-insertion-time
   bound on worst-case storage, independent of (1).
3. **Never cache a rejection.** A 409 (claim validation failure) is
   produced by `api/routes_api.py` before this module is ever called for
   that request -- `store()` is only reachable after
   `validate_artifact_claims` returns no findings. See
   `ArtifactCacheNeverStores409Test` in `api/test_api.py`.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from storage.models import ArtifactCacheRecord

MAX_CACHE_ROWS = 500


def cache_key(opportunity_id: str, truth_pack_hash: str, template_id: str, artifact_kind: str) -> str:
    """Deterministic key from the four-part identity BRIEF-FR-006 D2
    specifies (`(opportunity_id, truth_pack_hash, template_id,
    artifact_kind)`). Hashed rather than concatenated raw so it fits the
    `cache_key` column and never collides across parts via an embedded
    separator character."""
    raw = "|".join((opportunity_id, truth_pack_hash, template_id, artifact_kind))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(
    session: Session, opportunity_id: str, truth_pack_hash: str, template_id: str, artifact_kind: str,
) -> tuple[str, bytes] | None:
    """Returns `(content_type, payload)` on a cache hit, else `None`."""
    key = cache_key(opportunity_id, truth_pack_hash, template_id, artifact_kind)
    row = session.query(ArtifactCacheRecord).filter_by(cache_key=key).first()
    if row is None:
        return None
    return row.content_type, row.payload


def store(
    session: Session,
    opportunity_id: str,
    truth_pack_hash: str,
    template_id: str,
    artifact_kind: str,
    content_type: str,
    payload: bytes,
) -> None:
    """Writes a validated artifact's bytes to the cache. Callers must never
    reach this for a 409 rejection -- see module docstring point 3."""
    key = cache_key(opportunity_id, truth_pack_hash, template_id, artifact_kind)

    existing = session.query(ArtifactCacheRecord).filter_by(cache_key=key).first()
    if existing is not None:
        return  # already cached under this exact key -- idempotent write

    # Policy (1): drop stale generations for this same
    # (opportunity, kind, template) under a since-changed truth-pack hash.
    session.query(ArtifactCacheRecord).filter(
        ArtifactCacheRecord.opportunity_id == opportunity_id,
        ArtifactCacheRecord.artifact_kind == artifact_kind,
        ArtifactCacheRecord.template_id == template_id,
        ArtifactCacheRecord.truth_pack_hash != truth_pack_hash,
    ).delete(synchronize_session=False)

    session.add(
        ArtifactCacheRecord(
            cache_key=key,
            opportunity_id=opportunity_id,
            truth_pack_hash=truth_pack_hash,
            template_id=template_id,
            artifact_kind=artifact_kind,
            content_type=content_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    # Policy (2): global row cap, oldest first.
    total = session.query(ArtifactCacheRecord).count()
    if total > MAX_CACHE_ROWS:
        overflow = total - MAX_CACHE_ROWS
        stale_keys = [
            row.cache_key
            for row in session.query(ArtifactCacheRecord)
            .order_by(ArtifactCacheRecord.created_at.asc())
            .limit(overflow)
            .all()
        ]
        if stale_keys:
            session.query(ArtifactCacheRecord).filter(
                ArtifactCacheRecord.cache_key.in_(stale_keys)
            ).delete(synchronize_session=False)
            session.commit()


def docx_kind(kind: str) -> str:
    """`artifact_kind` value for the DOCX generation of `kind`
    (`"cv"`/`"cover-letter"`) -- unchanged from before D2 so pre-existing
    rows (there are none yet; migration 0004 shipped empty) and the
    pre-existing DOCX routes keep their historical key shape."""
    return kind


def pdf_kind(kind: str) -> str:
    """`artifact_kind` value for the PDF generation of `kind` -- distinct
    from `docx_kind` so a PDF and a DOCX for the same opportunity/template
    never collide under one cache row despite the table having no separate
    format column."""
    return f"{kind}-pdf"
