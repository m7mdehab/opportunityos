"""Read-only bounded selection for the employment reevaluation pipeline.

This module deliberately selects IDs only. It does not load job content,
score opportunities, enqueue worker jobs, or write canonical state.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from storage.models import OpportunityRecord

DEFAULT_REEVALUATION_BATCH_SIZE = 100
MAX_REEVALUATION_BATCH_SIZE = 100
_MAX_CURSOR_LENGTH = 64


@dataclass(frozen=True, slots=True)
class ReevaluationBatch:
    """One deterministic employment-only keyset page of opaque opportunity IDs."""

    start_after: str | None
    opportunity_ids: tuple[str, ...]
    next_cursor: str | None
    has_more: bool

    @property
    def selected_count(self) -> int:
        return len(self.opportunity_ids)


def select_reevaluation_batch(
    session: Session,
    *,
    start_after: str | None = None,
    batch_size: int = DEFAULT_REEVALUATION_BATCH_SIZE,
) -> ReevaluationBatch:
    """Select at most 100 employment opportunity IDs without writing or hydrating content.

    A single look-ahead ID determines ``has_more``. The cursor is exclusive,
    so a caller can resume after a completed batch without offset scans. On an
    interrupted consumer, replaying the prior cursor is safe when its writer
    uses the existing per-truth-pack evaluation upsert.
    """
    if type(batch_size) is not int:
        raise TypeError("batch_size must be an integer")
    if not 1 <= batch_size <= MAX_REEVALUATION_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be between 1 and {MAX_REEVALUATION_BATCH_SIZE}"
        )
    if start_after is not None:
        if not isinstance(start_after, str):
            raise TypeError("start_after must be a string or None")
        if (
            not start_after
            or start_after != start_after.strip()
            or len(start_after) > _MAX_CURSOR_LENGTH
            or any(ord(char) < 32 or ord(char) == 127 for char in start_after)
        ):
            raise ValueError("start_after must be a non-empty opaque opportunity ID")

    query = (
        session.query(OpportunityRecord.id)
        .filter(OpportunityRecord.track == "employment")
        .order_by(OpportunityRecord.id.asc())
    )
    if start_after is not None:
        query = query.filter(OpportunityRecord.id > start_after)

    candidates = [row[0] for row in query.limit(batch_size + 1).all()]
    selected = tuple(candidates[:batch_size])
    return ReevaluationBatch(
        start_after=start_after,
        opportunity_ids=selected,
        next_cursor=selected[-1] if selected else start_after,
        has_more=len(candidates) > batch_size,
    )
