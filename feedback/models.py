from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class FeedbackLabel(str, Enum):
    GOOD_MATCH = "good_match"
    BAD_MATCH = "bad_match"
    ELIGIBILITY_WRONG = "eligibility_wrong"
    SENIORITY_WRONG = "seniority_wrong"
    IRRELEVANT_ROLE = "irrelevant_role"
    SOURCE_QUALITY_ISSUE = "source_quality_issue"
    DUPLICATE_ISSUE = "duplicate_issue"
    REVIEW_REQUIRED = "review_required"

@dataclass(frozen=True, slots=True)
class FounderFeedbackEvent:
    id: str
    opportunity_id: str
    feedback_label: FeedbackLabel
    structured_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = ""
