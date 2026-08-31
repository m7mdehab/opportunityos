import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from feedback.models import FounderFeedbackEvent, FeedbackLabel
from storage.repository import StorageRepository

class FounderFeedbackService:
    def __init__(self, repository: StorageRepository):
        self.repo = repository

    def submit_feedback(
        self,
        opportunity_id: str,
        label: FeedbackLabel,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> FounderFeedbackEvent:
        now_iso = datetime.now(timezone.utc).isoformat()
        rec_id = hashlib.sha256(f"{opportunity_id}:{label.value}:{now_iso}".encode("utf-8")).hexdigest()[:16]
        
        self.repo.record_feedback(
            opp_id=opportunity_id,
            label=label.value,
            reason=reason,
            notes=notes,
        )
        return FounderFeedbackEvent(
            id=rec_id,
            opportunity_id=opportunity_id,
            feedback_label=label,
            structured_reason=reason,
            notes=notes,
            created_at=now_iso,
        )
