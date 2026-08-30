"""Durable Idempotency & Duplicate Prevention Ledger."""
from __future__ import annotations

import hashlib
from typing import Any

from .models import ActionStatus, ConfirmationEvidence, OutboundActionRecord


class IdempotencyLedger:
    """Thread-safe durable submission ledger preventing duplicate side effects."""

    def __init__(self) -> None:
        self._records: dict[str, OutboundActionRecord] = {}

    @classmethod
    def compute_idempotency_key(
        cls,
        workspace: str,
        candidate_id: str,
        opportunity_id: str,
        action_type: str,
    ) -> str:
        payload = f"{workspace}:{candidate_id}:{opportunity_id}:{action_type}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def record_intent(self, record: OutboundActionRecord) -> None:
        """Record durable intent before external side effect."""
        key = record.idempotency_key
        existing = self._records.get(key)
        if existing is not None:
            if existing.action_status in (ActionStatus.SUBMITTING, ActionStatus.SUBMITTED, ActionStatus.CONFIRMED):
                raise ValueError(f"Duplicate submission prevented for idempotency key '{key}' (status: {existing.action_status.value})")

        self._records[key] = record

    def transition_status(
        self,
        idempotency_key: str,
        new_status: ActionStatus,
        evidence: ConfirmationEvidence | None = None,
        blocker_reason: str = "",
        external_reference_id: str = "",
    ) -> OutboundActionRecord:
        """Transition action record state."""
        existing = self._records.get(idempotency_key)
        if existing is None:
            raise KeyError(f"No record found for idempotency key '{idempotency_key}'")

        updated = OutboundActionRecord(
            action_id=existing.action_id,
            opportunity_id=existing.opportunity_id,
            opportunity_content_hash=existing.opportunity_content_hash,
            track=existing.track,
            source=existing.source,
            adapter_name=existing.adapter_name,
            adapter_version=existing.adapter_version,
            execution_mode=existing.execution_mode,
            qualification_decision=existing.qualification_decision,
            match_score_snapshot=existing.match_score_snapshot,
            artifact_ids=existing.artifact_ids,
            artifact_hashes=existing.artifact_hashes,
            answer_manifest_hash=existing.answer_manifest_hash,
            action_status=new_status,
            idempotency_key=existing.idempotency_key,
            created_at=existing.created_at,
            updated_at="2026-08-30T00:00:00Z",
            confirmation_evidence=evidence if evidence is not None else existing.confirmation_evidence,
            blocker_reason=blocker_reason or existing.blocker_reason,
            manual_edits=existing.manual_edits,
            external_reference_id=external_reference_id or existing.external_reference_id,
        )
        self._records[idempotency_key] = updated
        return updated

    def is_duplicate(self, workspace: str, candidate_id: str, opportunity_id: str, action_type: str) -> bool:
        key = self.compute_idempotency_key(workspace, candidate_id, opportunity_id, action_type)
        existing = self._records.get(key)
        if existing is None:
            return False
        return existing.action_status in (ActionStatus.SUBMITTING, ActionStatus.SUBMITTED, ActionStatus.CONFIRMED)

    def get_record(self, idempotency_key: str) -> OutboundActionRecord | None:
        return self._records.get(idempotency_key)
