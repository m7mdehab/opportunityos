import os
import sys
import json
import argparse
from datetime import datetime, timezone
from storage.engine import get_engine, init_db, get_session_factory
from storage.models import (
    Base,
    OpportunityRecord,
    FieldProvenanceRecord,
    OutboundActionRecordModel,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
    WorkerJobRecord,
    FounderFeedbackRecord,
)


def dump_database(db_url: str, output_file: str) -> int:
    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    session = session_factory()

    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "opportunities": [],
        "field_provenances": [],
        "outbound_actions": [],
        "idempotency_reservations": [],
        "inbound_evidence": [],
        "pipeline_events": [],
        "founder_notifications": [],
        "inbox_checkpoints": [],
        "reconciliation_records": [],
        "worker_jobs": [],
        "founder_feedback": [],
    }

    # 1. Opportunities & Field Provenances
    for opp in session.query(OpportunityRecord).all():
        data["opportunities"].append({
            "id": opp.id, "track": opp.track, "title": opp.title, "organization": opp.organization,
            "description": opp.description, "source_id": opp.source_id, "source_url": opp.source_url,
            "content_hash": opp.content_hash, "country": opp.country, "region": opp.region,
            "geographic_scope": opp.geographic_scope, "posted_date": opp.posted_date, "deadline": opp.deadline,
            "is_stale": opp.is_stale, "reverified_at": opp.reverified_at.isoformat() if opp.reverified_at else None,
            "raw_payload_json": opp.raw_payload_json, "created_at": opp.created_at.isoformat() if opp.created_at else None,
        })
        for prov in opp.provenances:
            data["field_provenances"].append({
                "opportunity_id": prov.opportunity_id, "field_name": prov.field_name,
                "raw_value": prov.raw_value, "normalized_value": prov.normalized_value,
                "derivation_type": prov.derivation_type, "raw_pointer": prov.raw_pointer,
                "record_checksum": prov.record_checksum, "rule_id": prov.rule_id,
            })

    # 2. Outbound Actions
    for act in session.query(OutboundActionRecordModel).all():
        data["outbound_actions"].append({
            "id": act.id, "opportunity_id": act.opportunity_id,
            "opportunity_content_hash": act.opportunity_content_hash,
            "workspace": act.workspace, "candidate_id": act.candidate_id, "track": act.track,
            "source": act.source, "adapter_name": act.adapter_name, "adapter_version": act.adapter_version,
            "execution_mode": act.execution_mode, "qualification_decision": act.qualification_decision,
            "match_score_snapshot": act.match_score_snapshot, "artifact_ids_json": act.artifact_ids_json,
            "artifact_hashes_json": act.artifact_hashes_json, "manifest_hash": act.manifest_hash,
            "action_status": act.action_status, "idempotency_key": act.idempotency_key,
            "receipt_reference": act.receipt_reference, "confirmation_text": act.confirmation_text,
            "receipt_checksum": act.receipt_checksum,
            "confirmation_evidence_json": act.confirmation_evidence_json,
            "blocker_reason": act.blocker_reason, "manual_edits_json": act.manual_edits_json,
            "external_reference_id": act.external_reference_id, "record_json": act.record_json,
            "created_at": act.created_at.isoformat() if act.created_at else None,
            "updated_at": act.updated_at.isoformat() if act.updated_at else None,
        })

    # 3. Idempotency Reservations
    for res in session.query(IdempotencyReservationRecord).all():
        data["idempotency_reservations"].append({
            "idempotency_key": res.idempotency_key, "action_id": res.action_id,
            "workspace": res.workspace, "candidate_id": res.candidate_id,
            "opportunity_id": res.opportunity_id, "action_type": res.action_type,
            "action_status": res.action_status, "record_json": res.record_json,
            "created_at": res.created_at.isoformat() if res.created_at else None,
            "updated_at": res.updated_at.isoformat() if res.updated_at else None,
        })

    # 4. Inbound Evidence
    for ev in session.query(InboundEvidenceRecord).all():
        data["inbound_evidence"].append({
            "message_content_hash": ev.message_content_hash, "provider": ev.provider,
            "provider_message_id": ev.provider_message_id, "thread_id": ev.thread_id,
            "sender_email": ev.sender_email, "sender_name": ev.sender_name,
            "recipient_email": ev.recipient_email, "subject": ev.subject,
            "snippet": ev.snippet, "body_text": ev.body_text, "body_html": ev.body_html,
            "received_at": ev.received_at.isoformat() if ev.received_at else None,
            "headers_json": ev.headers_json, "attachment_names_json": ev.attachment_names_json,
            "processing_status": ev.processing_status,
            "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
        })

    # 5. Pipeline Events
    for evt in session.query(PipelineEventRecord).all():
        data["pipeline_events"].append({
            "event_id": evt.event_id, "opportunity_id": evt.opportunity_id, "signal_id": evt.signal_id,
            "previous_stage": evt.previous_stage, "new_stage": evt.new_stage, "track": evt.track,
            "trigger_category": evt.trigger_category, "message_content_hash": evt.message_content_hash,
            "occurred_at": evt.occurred_at.isoformat() if evt.occurred_at else None,
            "recorded_at": evt.recorded_at.isoformat() if evt.recorded_at else None,
            "actor": evt.actor, "notes": evt.notes,
        })

    # 6. Founder Notifications
    for notif in session.query(NotificationRecord).all():
        data["founder_notifications"].append({
            "notification_key": notif.notification_key, "notification_id": notif.notification_id,
            "opportunity_id": notif.opportunity_id, "signal_id": notif.signal_id,
            "priority": notif.priority, "category": notif.category, "title": notif.title,
            "message": notif.message, "action_required": notif.action_required,
            "deadline": notif.deadline,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
            "acknowledged": notif.acknowledged,
            "acknowledged_at": notif.acknowledged_at.isoformat() if notif.acknowledged_at else None,
        })

    # 7. Checkpoints
    for chk in session.query(InboxCheckpointRecord).all():
        data["inbox_checkpoints"].append({
            "checkpoint_key": chk.checkpoint_key, "cursor_value": chk.cursor_value,
            "updated_at": chk.updated_at.isoformat() if chk.updated_at else None,
        })

    # 8. Reconciliations
    for rec in session.query(ReconciliationRecordModel).all():
        data["reconciliation_records"].append({
            "reconciliation_id": rec.reconciliation_id, "outbound_action_id": rec.outbound_action_id,
            "opportunity_id": rec.opportunity_id, "signal_id": rec.signal_id,
            "inbound_content_hash": rec.inbound_content_hash, "reason": rec.reason,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "resolved": rec.resolved,
            "resolved_at": rec.resolved_at.isoformat() if rec.resolved_at else None,
        })

    # 9. Worker Jobs
    for job in session.query(WorkerJobRecord).all():
        data["worker_jobs"].append({
            "id": job.id, "job_type": job.job_type, "payload_json": job.payload_json,
            "status": job.status, "run_after": job.run_after.isoformat() if job.run_after else None,
            "retry_count": job.retry_count, "max_retries": job.max_retries,
            "lease_owner": job.lease_owner,
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        })

    # 10. Founder Feedback
    for fb in session.query(FounderFeedbackRecord).all():
        data["founder_feedback"].append({
            "id": fb.id, "opportunity_id": fb.opportunity_id, "feedback_label": fb.feedback_label,
            "structured_reason": fb.structured_reason, "notes": fb.notes, "dedup_hash": fb.dedup_hash,
            "created_at": fb.created_at.isoformat() if fb.created_at else None,
        })

    session.close()
    engine.dispose()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return len(data["opportunities"])


def restore_database(dump_file: str, db_url: str) -> None:
    with open(dump_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    engine = get_engine(db_url)
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    # 1. Opportunities & Provenances
    for opp_dict in data.get("opportunities", []):
        if opp_dict.get("reverified_at"):
            opp_dict["reverified_at"] = datetime.fromisoformat(opp_dict["reverified_at"])
        if opp_dict.get("created_at"):
            opp_dict["created_at"] = datetime.fromisoformat(opp_dict["created_at"])
        opp = OpportunityRecord(**opp_dict)
        session.merge(opp)

    for prov_dict in data.get("field_provenances", []):
        prov = FieldProvenanceRecord(**prov_dict)
        session.add(prov)

    # 2. Outbound Actions
    for act_dict in data.get("outbound_actions", []):
        if act_dict.get("created_at"):
            act_dict["created_at"] = datetime.fromisoformat(act_dict["created_at"])
        if act_dict.get("updated_at"):
            act_dict["updated_at"] = datetime.fromisoformat(act_dict["updated_at"])
        act = OutboundActionRecordModel(**act_dict)
        session.merge(act)

    # 3. Idempotency Reservations
    for res_dict in data.get("idempotency_reservations", []):
        if res_dict.get("created_at"):
            res_dict["created_at"] = datetime.fromisoformat(res_dict["created_at"])
        if res_dict.get("updated_at"):
            res_dict["updated_at"] = datetime.fromisoformat(res_dict["updated_at"])
        res = IdempotencyReservationRecord(**res_dict)
        session.merge(res)

    # 4. Inbound Evidence
    for ev_dict in data.get("inbound_evidence", []):
        if ev_dict.get("received_at"):
            ev_dict["received_at"] = datetime.fromisoformat(ev_dict["received_at"])
        if ev_dict.get("processed_at"):
            ev_dict["processed_at"] = datetime.fromisoformat(ev_dict["processed_at"])
        ev = InboundEvidenceRecord(**ev_dict)
        session.merge(ev)

    # 5. Pipeline Events
    for evt_dict in data.get("pipeline_events", []):
        if evt_dict.get("source_timestamp"):
            evt_dict["source_timestamp"] = datetime.fromisoformat(evt_dict["source_timestamp"])
        if evt_dict.get("occurred_at"):
            evt_dict["occurred_at"] = datetime.fromisoformat(evt_dict["occurred_at"])
        if evt_dict.get("recorded_at"):
            evt_dict["recorded_at"] = datetime.fromisoformat(evt_dict["recorded_at"])
        evt = PipelineEventRecord(**evt_dict)
        session.merge(evt)

    # 6. Founder Notifications
    for notif_dict in data.get("founder_notifications", []):
        if notif_dict.get("created_at"):
            notif_dict["created_at"] = datetime.fromisoformat(notif_dict["created_at"])
        if notif_dict.get("acknowledged_at"):
            notif_dict["acknowledged_at"] = datetime.fromisoformat(notif_dict["acknowledged_at"])
        notif = NotificationRecord(**notif_dict)
        session.merge(notif)

    # 7. Checkpoints
    for chk_dict in data.get("inbox_checkpoints", []):
        if chk_dict.get("updated_at"):
            chk_dict["updated_at"] = datetime.fromisoformat(chk_dict["updated_at"])
        chk = InboxCheckpointRecord(**chk_dict)
        session.merge(chk)

    # 8. Reconciliations
    for rec_dict in data.get("reconciliation_records", []):
        if rec_dict.get("created_at"):
            rec_dict["created_at"] = datetime.fromisoformat(rec_dict["created_at"])
        if rec_dict.get("resolved_at"):
            rec_dict["resolved_at"] = datetime.fromisoformat(rec_dict["resolved_at"])
        rec = ReconciliationRecordModel(**rec_dict)
        session.merge(rec)

    # 9. Worker Jobs
    for job_dict in data.get("worker_jobs", []):
        if job_dict.get("run_after"):
            job_dict["run_after"] = datetime.fromisoformat(job_dict["run_after"])
        if job_dict.get("lease_expires_at"):
            job_dict["lease_expires_at"] = datetime.fromisoformat(job_dict["lease_expires_at"])
        if job_dict.get("created_at"):
            job_dict["created_at"] = datetime.fromisoformat(job_dict["created_at"])
        if job_dict.get("updated_at"):
            job_dict["updated_at"] = datetime.fromisoformat(job_dict["updated_at"])
        job = WorkerJobRecord(**job_dict)
        session.merge(job)

    # 10. Founder Feedback
    for fb_dict in data.get("founder_feedback", []):
        if fb_dict.get("created_at"):
            fb_dict["created_at"] = datetime.fromisoformat(fb_dict["created_at"])
        fb = FounderFeedbackRecord(**fb_dict)
        session.merge(fb)

    session.commit()
    session.close()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="OpportunityOS Database Backup and Restore")
    subparsers = parser.add_subparsers(dest="command")

    dump_p = subparsers.add_parser("dump")
    dump_p.add_argument("--db-url", default=os.environ.get("OPPORTUNITYOS_DB_URL", "sqlite:///opportunityos.db"))
    dump_p.add_argument("--out", required=True)

    restore_p = subparsers.add_parser("restore")
    restore_p.add_argument("--file", required=True)
    restore_p.add_argument("--db-url", default=os.environ.get("OPPORTUNITYOS_DB_URL", "sqlite:///opportunityos.db"))

    args = parser.parse_args()
    if args.command == "dump":
        dump_database(args.db_url, args.out)
    elif args.command == "restore":
        restore_database(args.file, args.db_url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
