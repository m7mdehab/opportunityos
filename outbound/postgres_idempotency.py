import json
import hashlib
import dataclasses
from datetime import datetime, timezone
from typing import Optional, Sequence, List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, and_
from storage.engine import get_engine, get_session_factory, get_production_db_url
from storage.models import IdempotencyReservationRecord, OutboundActionRecordModel
from outbound.models import (
    ActionStatus,
    ConfirmationEvidence,
    ExecutionMode,
    OutboundActionRecord,
)
from outbound.idempotency import DuplicateSubmissionError, UnknownOutcomeFrozenError


class PostgresIdempotencyLedger:
    """Thread-safe and process-durable PostgreSQL/Relational Idempotency Ledger with atomic concurrency."""

    def __init__(self, db_url: Optional[str] = None, session: Optional[Session] = None):
        self._external_session = session
        if self._external_session is None:
            self.db_url = get_production_db_url(db_url)
            self.engine = get_engine(self.db_url)
            self.session_factory = get_session_factory(self.engine)
        else:
            if db_url is not None:
                self.db_url = get_production_db_url(db_url)
            else:
                self.db_url = None
            self.engine = None
            self.session_factory = None

    def _get_session(self) -> Session:
        if self._external_session is not None:
            return self._external_session
        return self.session_factory()

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

    def reserve_submission(self, record: OutboundActionRecord) -> None:
        """Atomically reserve submission intent across independent ledger instances."""
        idempotency_key = record.idempotency_key
        submitting_record = dataclasses.replace(
            record,
            action_status=ActionStatus.SUBMITTING,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        rec_json = self._record_to_json(submitting_record)

        session = self._get_session()
        owns_session = self._external_session is None

        try:
            # 1. Check if existing reservation exists
            existing = session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).first()
            if existing:
                if existing.action_status == ActionStatus.UNKNOWN_OUTCOME.value:
                    raise UnknownOutcomeFrozenError(
                        f"Action {existing.action_id} is permanently frozen in UNKNOWN_OUTCOME. Automatic replay blocked."
                    )
                if existing.action_status in (ActionStatus.SUBMITTING.value, ActionStatus.SUBMITTED.value, ActionStatus.CONFIRMED.value, ActionStatus.PLANNED.value):
                    raise DuplicateSubmissionError(
                        f"Duplicate submission blocked for idempotency key {idempotency_key} (current status: {existing.action_status})"
                    )

            now = datetime.now(timezone.utc)

            # 2. Atomic insert
            reservation = IdempotencyReservationRecord(
                idempotency_key=idempotency_key,
                action_id=record.action_id,
                workspace=record.workspace,
                candidate_id=record.candidate_id,
                opportunity_id=record.opportunity_id,
                action_type="application",
                action_status=ActionStatus.SUBMITTING.value,
                record_json=rec_json,
                created_at=now,
                updated_at=now,
            )
            session.add(reservation)
            session.commit()
        except Exception as e:
            session.rollback()
            if isinstance(e, (DuplicateSubmissionError, UnknownOutcomeFrozenError)):
                raise
            if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "integrityerror" in str(e).lower() or "uniqueconstraint" in str(e).lower():
                # Re-query status to raise appropriate domain exception
                existing = session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).first()
                if existing and existing.action_status == ActionStatus.UNKNOWN_OUTCOME.value:
                    raise UnknownOutcomeFrozenError(
                        f"Action {existing.action_id} is permanently frozen in UNKNOWN_OUTCOME."
                    )
                raise DuplicateSubmissionError(
                    f"Concurrent duplicate submission prevented for idempotency key {idempotency_key}"
                )
            raise
        finally:
            if owns_session:
                session.close()

    def transition_status(
        self,
        idempotency_key: str,
        new_status: ActionStatus,
        evidence: Optional[ConfirmationEvidence] = None,
        blocker_reason: str = "",
    ) -> OutboundActionRecord:
        """Update record status in PostgreSQL ledger atomically."""
        session = self._get_session()
        owns_session = self._external_session is None

        try:
            res = session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).first()
            if not res or not res.record_json:
                raise KeyError(f"No record found with idempotency_key: {idempotency_key}")

            old_rec = self._json_to_record(res.record_json)
            now_iso = datetime.now(timezone.utc).isoformat()
            now_dt = datetime.now(timezone.utc)
            updated_rec = dataclasses.replace(
                old_rec,
                action_status=new_status,
                confirmation_evidence=evidence or old_rec.confirmation_evidence,
                blocker_reason=blocker_reason or old_rec.blocker_reason,
                updated_at=now_iso,
            )
            new_json = self._record_to_json(updated_rec)

            res.action_status = new_status.value
            res.record_json = new_json
            res.updated_at = now_dt

            # Sync to OutboundActionRecordModel
            ev_dict = None
            if updated_rec.confirmation_evidence:
                ev_dict = {
                    "confirmed": updated_rec.confirmation_evidence.confirmed,
                    "confirmation_text": updated_rec.confirmation_evidence.confirmation_text,
                    "application_id": updated_rec.confirmation_evidence.application_id,
                    "receipt_reference": updated_rec.confirmation_evidence.receipt_reference,
                    "final_url": updated_rec.confirmation_evidence.final_url,
                    "detected_at": updated_rec.confirmation_evidence.detected_at,
                    "evidence_checksum": updated_rec.confirmation_evidence.evidence_checksum,
                }

            c_at = datetime.fromisoformat(updated_rec.created_at) if updated_rec.created_at else now_dt
            u_at = now_dt

            act_model = OutboundActionRecordModel(
                id=updated_rec.action_id,
                opportunity_id=updated_rec.opportunity_id,
                opportunity_content_hash=updated_rec.opportunity_content_hash,
                workspace=updated_rec.workspace,
                candidate_id=updated_rec.candidate_id,
                track=updated_rec.track.value,
                source=updated_rec.source,
                adapter_name=updated_rec.adapter_name,
                adapter_version=updated_rec.adapter_version,
                execution_mode=updated_rec.execution_mode.value,
                qualification_decision=updated_rec.qualification_decision.value,
                match_score_snapshot=float(updated_rec.match_score_snapshot),
                artifact_ids_json=json.dumps(list(updated_rec.artifact_ids)),
                artifact_hashes_json=json.dumps(list(updated_rec.artifact_hashes)),
                manifest_hash=updated_rec.manifest_hash,
                action_status=updated_rec.action_status.value,
                idempotency_key=updated_rec.idempotency_key,
                receipt_reference=updated_rec.confirmation_evidence.receipt_reference if updated_rec.confirmation_evidence else None,
                confirmation_text=updated_rec.confirmation_evidence.confirmation_text if updated_rec.confirmation_evidence else None,
                receipt_checksum=updated_rec.confirmation_evidence.evidence_checksum if updated_rec.confirmation_evidence else None,
                confirmation_evidence_json=json.dumps(ev_dict) if ev_dict else None,
                blocker_reason=updated_rec.blocker_reason,
                manual_edits_json=json.dumps(list(updated_rec.manual_edits)),
                external_reference_id=updated_rec.external_reference_id,
                record_json=new_json,
                created_at=c_at,
                updated_at=u_at,
            )
            session.merge(act_model)
            session.commit()
            return updated_rec
        except Exception:
            session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def record_outcome(self, record: OutboundActionRecord) -> None:
        session = self._get_session()
        owns_session = self._external_session is None

        try:
            now = datetime.now(timezone.utc)
            rec_json = self._record_to_json(record)

            reservation = session.query(IdempotencyReservationRecord).filter_by(idempotency_key=record.idempotency_key).first()
            if reservation:
                reservation.action_status = record.action_status.value
                reservation.record_json = rec_json
                reservation.updated_at = now
            else:
                reservation = IdempotencyReservationRecord(
                    idempotency_key=record.idempotency_key,
                    action_id=record.action_id,
                    workspace=record.workspace,
                    candidate_id=record.candidate_id,
                    opportunity_id=record.opportunity_id,
                    action_type="application",
                    action_status=record.action_status.value,
                    record_json=rec_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(reservation)

            ev_dict = None
            if record.confirmation_evidence:
                ev_dict = {
                    "confirmed": record.confirmation_evidence.confirmed,
                    "confirmation_text": record.confirmation_evidence.confirmation_text,
                    "application_id": record.confirmation_evidence.application_id,
                    "receipt_reference": record.confirmation_evidence.receipt_reference,
                    "final_url": record.confirmation_evidence.final_url,
                    "detected_at": record.confirmation_evidence.detected_at,
                    "evidence_checksum": record.confirmation_evidence.evidence_checksum,
                }

            c_at = datetime.fromisoformat(record.created_at) if record.created_at else now
            u_at = datetime.fromisoformat(record.updated_at) if record.updated_at else now

            act_model = OutboundActionRecordModel(
                id=record.action_id,
                opportunity_id=record.opportunity_id,
                opportunity_content_hash=record.opportunity_content_hash,
                workspace=record.workspace,
                candidate_id=record.candidate_id,
                track=record.track.value,
                source=record.source,
                adapter_name=record.adapter_name,
                adapter_version=record.adapter_version,
                execution_mode=record.execution_mode.value,
                qualification_decision=record.qualification_decision.value,
                match_score_snapshot=float(record.match_score_snapshot),
                artifact_ids_json=json.dumps(list(record.artifact_ids)),
                artifact_hashes_json=json.dumps(list(record.artifact_hashes)),
                manifest_hash=record.manifest_hash,
                action_status=record.action_status.value,
                idempotency_key=record.idempotency_key,
                receipt_reference=record.confirmation_evidence.receipt_reference if record.confirmation_evidence else None,
                confirmation_text=record.confirmation_evidence.confirmation_text if record.confirmation_evidence else None,
                receipt_checksum=record.confirmation_evidence.evidence_checksum if record.confirmation_evidence else None,
                confirmation_evidence_json=json.dumps(ev_dict) if ev_dict else None,
                blocker_reason=record.blocker_reason,
                manual_edits_json=json.dumps(list(record.manual_edits)),
                external_reference_id=record.external_reference_id,
                record_json=rec_json,
                created_at=c_at,
                updated_at=u_at,
            )
            session.merge(act_model)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def get_record(self, workspace: str, candidate_id: str | None = None, opportunity_id: str | None = None, action_type: str = "application") -> Optional[OutboundActionRecord]:
        """Support querying by (workspace, candidate_id, opportunity_id, action_type) or directly by idempotency_key."""
        if candidate_id is None and opportunity_id is None:
            # Called with idempotency_key directly
            idempotency_key = workspace
        else:
            idempotency_key = self.compute_idempotency_key(workspace, candidate_id, opportunity_id, action_type)

        session = self._get_session()
        owns_session = self._external_session is None
        try:
            res = session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).first()
            if not res or not res.record_json:
                return None
            return self._json_to_record(res.record_json)
        finally:
            if owns_session:
                session.close()

    def is_duplicate(self, workspace: str, candidate_id: str, opportunity_id: str, action_type: str = "application") -> bool:
        rec = self.get_record(workspace, candidate_id, opportunity_id, action_type)
        if rec is None:
            return False
        return rec.action_status in (
            ActionStatus.SUBMITTING,
            ActionStatus.SUBMITTED,
            ActionStatus.CONFIRMED,
            ActionStatus.UNKNOWN_OUTCOME,
        )

    def is_known(self, idempotency_key: str) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            return session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).count() > 0
        finally:
            if owns_session:
                session.close()

    def reconcile_unknown_outcome(
        self,
        idempotency_key: str,
        new_status: ActionStatus,
        reason: str = "Manual founder reconciliation",
    ) -> OutboundActionRecord:
        if new_status not in (ActionStatus.CONFIRMED, ActionStatus.FAILED, ActionStatus.BLOCKED):
            raise ValueError(f"Can only reconcile UNKNOWN_OUTCOME to CONFIRMED, FAILED, or BLOCKED, not {new_status}")
        return self.transition_status(
            idempotency_key=idempotency_key,
            new_status=new_status,
            blocker_reason=f"Reconciled from UNKNOWN_OUTCOME: {reason}",
        )

    def _record_to_json(self, record: OutboundActionRecord) -> str:
        evidence_dict = None
        if record.confirmation_evidence:
            evidence_dict = {
                "confirmed": record.confirmation_evidence.confirmed,
                "confirmation_text": record.confirmation_evidence.confirmation_text,
                "application_id": record.confirmation_evidence.application_id,
                "receipt_reference": record.confirmation_evidence.receipt_reference,
                "final_url": record.confirmation_evidence.final_url,
                "detected_at": record.confirmation_evidence.detected_at,
                "evidence_checksum": record.confirmation_evidence.evidence_checksum,
            }

        data = {
            "action_id": record.action_id,
            "opportunity_id": record.opportunity_id,
            "opportunity_content_hash": record.opportunity_content_hash,
            "workspace": record.workspace,
            "candidate_id": record.candidate_id,
            "track": record.track.value,
            "source": record.source,
            "adapter_name": record.adapter_name,
            "adapter_version": record.adapter_version,
            "execution_mode": record.execution_mode.value,
            "qualification_decision": record.qualification_decision.value,
            "match_score_snapshot": record.match_score_snapshot,
            "artifact_ids": list(record.artifact_ids),
            "artifact_hashes": list(record.artifact_hashes),
            "manifest_hash": record.manifest_hash,
            "action_status": record.action_status.value,
            "idempotency_key": record.idempotency_key,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "confirmation_evidence": evidence_dict,
            "blocker_reason": record.blocker_reason,
            "manual_edits": list(record.manual_edits),
            "external_reference_id": record.external_reference_id,
        }
        return json.dumps(data, sort_keys=True)

    def _json_to_record(self, raw_json: str) -> OutboundActionRecord:
        from matching.models import Track, QualificationDecision
        d = json.loads(raw_json)
        ev = None
        if d.get("confirmation_evidence"):
            e = d["confirmation_evidence"]
            ev = ConfirmationEvidence(
                confirmed=e["confirmed"],
                confirmation_text=e["confirmation_text"],
                application_id=e.get("application_id", ""),
                receipt_reference=e.get("receipt_reference", ""),
                final_url=e.get("final_url", ""),
                detected_at=e.get("detected_at", "2026-08-30T00:00:00Z"),
                evidence_checksum=e.get("evidence_checksum", ""),
            )

        return OutboundActionRecord(
            action_id=d["action_id"],
            opportunity_id=d["opportunity_id"],
            opportunity_content_hash=d.get("opportunity_content_hash", ""),
            workspace=d["workspace"],
            candidate_id=d["candidate_id"],
            track=Track(d["track"]),
            source=d["source"],
            adapter_name=d["adapter_name"],
            adapter_version=d["adapter_version"],
            execution_mode=ExecutionMode(d["execution_mode"]),
            qualification_decision=QualificationDecision(d["qualification_decision"]),
            match_score_snapshot=float(d["match_score_snapshot"]),
            artifact_ids=tuple(d["artifact_ids"]),
            artifact_hashes=tuple(d["artifact_hashes"]),
            manifest_hash=d["manifest_hash"],
            action_status=ActionStatus(d["action_status"]),
            idempotency_key=d["idempotency_key"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            confirmation_evidence=ev,
            blocker_reason=d.get("blocker_reason", ""),
            manual_edits=tuple(d.get("manual_edits", ())),
            external_reference_id=d.get("external_reference_id", ""),
        )
