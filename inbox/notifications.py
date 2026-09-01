"""Priority & Action-Required Notification Engine with Stable Key Idempotency and Durable Store."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Sequence, Union
from .models import (
    CorrelationEvidence,
    FounderNotificationRecord,
    InboundSignal,
    SignalPriority,
)
from .persistence import DurableInboxStore
from .postgres_persistence import PostgresInboxStore


from storage.engine import ProductionDatabaseConfigurationError


class NotificationEngine:
    """Surfaces high-priority action-required alerts for founder with strict key idempotency."""

    def __init__(self, workspace: str = "default", candidate_id: str = "founder", store: Union[DurableInboxStore, PostgresInboxStore] | None = None) -> None:
        self.workspace = workspace
        self.candidate_id = candidate_id
        if store is not None:
            self.store = store
        else:
            try:
                self.store = PostgresInboxStore()
            except ProductionDatabaseConfigurationError:
                self.store = DurableInboxStore(":memory:")

    @classmethod
    def compute_notification_key(cls, workspace: str, candidate_id: str, signal_id: str, category: str) -> str:
        payload = f"{workspace}:{candidate_id}:{signal_id}:{category}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def compute_notification_id(cls, notification_key: str) -> str:
        return f"notif-{notification_key[:16]}"

    def process_signal(
        self,
        signal: InboundSignal,
        correlation: CorrelationEvidence | None = None,
    ) -> FounderNotificationRecord | None:
        """Generate notification record only for actionable or high-priority signals."""
        if signal.priority in (SignalPriority.LOW, SignalPriority.NOISE) and not signal.requires_founder_action:
            return None

        key = self.compute_notification_key(self.workspace, self.candidate_id, signal.signal_id, signal.category.value)
        notif_id = self.compute_notification_id(key)
        deadline_str = signal.deadline.raw_snippet if signal.deadline else None

        notif = FounderNotificationRecord(
            notification_id=notif_id, notification_key=key,
            opportunity_id=correlation.opportunity_id if correlation and correlation.is_authoritative else None,
            signal_id=signal.signal_id, priority=signal.priority, category=signal.category,
            title=f"[{signal.priority.value.upper()}] {signal.category.value.replace('_', ' ').title()}",
            message=signal.summary, action_required=signal.requires_founder_action,
            deadline=deadline_str, created_at=signal.detected_at,
        )
        inserted = self.store.store_notification(notif)
        return notif if inserted else None

    def get_active_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        return tuple([n for n in self.store.get_all_notifications() if not n.acknowledged])

    def acknowledge_notification(self, notification_key: str, acknowledged_at: str | None = None) -> bool:
        ts = acknowledged_at or datetime.now(timezone.utc).isoformat()
        return self.store.acknowledge_notification(notification_key, ts)
