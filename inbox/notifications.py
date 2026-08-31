"""Priority & Action-Required Notification Engine with Idempotency."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Sequence
from .models import (
    CorrelationEvidence,
    FounderNotificationRecord,
    InboundSignal,
    SignalPriority,
)


class NotificationEngine:
    """Surfaces high-priority action-required alerts for founder with strict key idempotency."""

    def __init__(self, workspace: str = "default", candidate_id: str = "founder") -> None:
        self.workspace = workspace
        self.candidate_id = candidate_id
        self._notifications_by_key: dict[str, FounderNotificationRecord] = {}

    @classmethod
    def compute_notification_key(cls, workspace: str, candidate_id: str, signal_id: str, category: str) -> str:
        payload = f"{workspace}:{candidate_id}:{signal_id}:{category}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def process_signal(
        self,
        signal: InboundSignal,
        correlation: CorrelationEvidence | None = None,
    ) -> FounderNotificationRecord | None:
        """Generate notification record only for actionable or high-priority signals."""
        # Routine confirmations, routine rejections, marketing -> silently processed (0 notification)
        if signal.priority in (SignalPriority.LOW, SignalPriority.NOISE) and not signal.requires_founder_action:
            return None

        key = self.compute_notification_key(self.workspace, self.candidate_id, signal.signal_id, signal.category.value)
        if key in self._notifications_by_key:
            return None  # Idempotent replay: zero duplicate alerts

        deadline_str = signal.deadline.raw_snippet if signal.deadline else None
        notif = FounderNotificationRecord(
            notification_id=f"notif-{uuid.uuid4().hex[:12]}", notification_key=key,
            opportunity_id=correlation.opportunity_id if correlation and correlation.is_authoritative else None,
            signal_id=signal.signal_id, priority=signal.priority, category=signal.category,
            title=f"[{signal.priority.value.upper()}] {signal.category.value.replace('_', ' ').title()}",
            message=signal.summary, action_required=signal.requires_founder_action,
            deadline=deadline_str, created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._notifications_by_key[key] = notif
        return notif

    def get_active_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        return tuple([n for n in self._notifications_by_key.values() if not n.acknowledged])

    def acknowledge_notification(self, notification_key: str) -> bool:
        if notification_key in self._notifications_by_key:
            old = self._notifications_by_key[notification_key]
            updated = FounderNotificationRecord(
                notification_id=old.notification_id, notification_key=old.notification_key,
                opportunity_id=old.opportunity_id, signal_id=old.signal_id, priority=old.priority,
                category=old.category, title=old.title, message=old.message,
                action_required=old.action_required, deadline=old.deadline,
                created_at=old.created_at, acknowledged=True,
                acknowledged_at=datetime.now(timezone.utc).isoformat(),
            )
            self._notifications_by_key[notification_key] = updated
            return True
        return False
