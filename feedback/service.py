from datetime import datetime, timezone
from typing import Optional, List
from feedback.models import FounderFeedbackEvent, FeedbackLabel
from storage.repository import StorageRepository


class FounderFeedbackService:
    """Provides founder feedback capture, deduplication, and persistence without mutating TruthGraph facts."""

    def __init__(self, repository: StorageRepository):
        self.repo = repository

    def submit_feedback(
        self,
        opportunity_id: str,
        label: FeedbackLabel,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> FounderFeedbackEvent:
        db_record = self.repo.record_feedback(
            opp_id=opportunity_id,
            label=label.value,
            reason=reason,
            notes=notes,
        )
        # Fix split identity bug: Return exact persisted record ID
        return FounderFeedbackEvent(
            id=db_record.id,
            opportunity_id=db_record.opportunity_id,
            feedback_label=FeedbackLabel(db_record.feedback_label),
            structured_reason=db_record.structured_reason,
            notes=db_record.notes,
            created_at=db_record.created_at.isoformat() if db_record.created_at else "",
        )
