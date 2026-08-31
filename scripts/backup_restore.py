import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timezone
from storage.engine import get_engine, init_db, get_session_factory
from storage.models import (
    Base,
    OpportunityRecord,
    FieldProvenanceRecord,
    OutboundActionRecord,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    WorkerJobRecord,
    FounderFeedbackRecord,
)

def dump_database(db_url: str, output_file: str):
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
        "notifications": [],
        "worker_jobs": [],
        "founder_feedback": [],
    }

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

    for act in session.query(OutboundActionRecord).all():
        data["outbound_actions"].append({
            "id": act.id, "opportunity_id": act.opportunity_id, "execution_mode": act.execution_mode,
            "action_status": act.action_status, "idempotency_key": act.idempotency_key,
            "prepared_manifest_hash": act.prepared_manifest_hash, "receipt_reference": act.receipt_reference,
            "confirmation_text": act.confirmation_text, "receipt_checksum": act.receipt_checksum,
            "error_message": act.error_message, "created_at": act.created_at.isoformat() if act.created_at else None,
            "updated_at": act.updated_at.isoformat() if act.updated_at else None,
        })

    for res in session.query(IdempotencyReservationRecord).all():
        data["idempotency_reservations"].append({
            "idempotency_key": res.idempotency_key, "action_id": res.action_id,
            "opportunity_id": res.opportunity_id, "status": res.status,
            "created_at": res.created_at.isoformat() if res.created_at else None,
        })

    for ev in session.query(InboundEvidenceRecord).all():
        data["inbound_evidence"].append({
            "id": ev.id, "message_id": ev.message_id, "source_provider": ev.source_provider,
            "sender": ev.sender, "subject": ev.subject, "body_hash": ev.body_hash,
            "received_at": ev.received_at.isoformat() if ev.received_at else None,
            "processing_status": ev.processing_status,
            "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
            "raw_headers_json": ev.raw_headers_json,
        })

    for evt in session.query(PipelineEventRecord).all():
        data["pipeline_events"].append({
            "id": evt.id, "opportunity_id": evt.opportunity_id, "signal_id": evt.signal_id,
            "signal_category": evt.signal_category,
            "source_timestamp": evt.source_timestamp.isoformat() if evt.source_timestamp else None,
            "confidence": evt.confidence, "provenance_hash": evt.provenance_hash,
            "event_metadata_json": evt.event_metadata_json,
            "created_at": evt.created_at.isoformat() if evt.created_at else None,
        })

    for notif in session.query(NotificationRecord).all():
        data["notifications"].append({
            "id": notif.id, "notification_key": notif.notification_key, "opportunity_id": notif.opportunity_id,
            "priority": notif.priority, "headline": notif.headline, "body": notif.body,
            "action_required": notif.action_required, "deadline": notif.deadline,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        })

    for job in session.query(WorkerJobRecord).all():
        data["worker_jobs"].append({
            "id": job.id, "job_type": job.job_type, "payload_json": job.payload_json,
            "status": job.status, "run_after": job.run_after.isoformat() if job.run_after else None,
            "retry_count": job.retry_count, "max_retries": job.max_retries,
            "lease_owner": job.lease_owner, "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "error_message": job.error_message, "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        })

    for fb in session.query(FounderFeedbackRecord).all():
        data["founder_feedback"].append({
            "id": fb.id, "opportunity_id": fb.opportunity_id, "feedback_label": fb.feedback_label,
            "structured_reason": fb.structured_reason, "notes": fb.notes,
            "created_at": fb.created_at.isoformat() if fb.created_at else None,
        })

    session.close()
    engine.dispose()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return len(data["opportunities"])

def restore_database(dump_file: str, db_url: str):
    with open(dump_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    engine = get_engine(db_url)
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

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

    for act_dict in data.get("outbound_actions", []):
        if act_dict.get("created_at"):
            act_dict["created_at"] = datetime.fromisoformat(act_dict["created_at"])
        if act_dict.get("updated_at"):
            act_dict["updated_at"] = datetime.fromisoformat(act_dict["updated_at"])
        act = OutboundActionRecord(**act_dict)
        session.merge(act)

    for res_dict in data.get("idempotency_reservations", []):
        if res_dict.get("created_at"):
            res_dict["created_at"] = datetime.fromisoformat(res_dict["created_at"])
        res = IdempotencyReservationRecord(**res_dict)
        session.merge(res)

    for ev_dict in data.get("inbound_evidence", []):
        if ev_dict.get("received_at"):
            ev_dict["received_at"] = datetime.fromisoformat(ev_dict["received_at"])
        if ev_dict.get("processed_at"):
            ev_dict["processed_at"] = datetime.fromisoformat(ev_dict["processed_at"])
        ev = InboundEvidenceRecord(**ev_dict)
        session.merge(ev)

    for evt_dict in data.get("pipeline_events", []):
        if evt_dict.get("source_timestamp"):
            evt_dict["source_timestamp"] = datetime.fromisoformat(evt_dict["source_timestamp"])
        if evt_dict.get("created_at"):
            evt_dict["created_at"] = datetime.fromisoformat(evt_dict["created_at"])
        evt = PipelineEventRecord(**evt_dict)
        session.merge(evt)

    for notif_dict in data.get("notifications", []):
        if notif_dict.get("created_at"):
            notif_dict["created_at"] = datetime.fromisoformat(notif_dict["created_at"])
        notif = NotificationRecord(**notif_dict)
        session.merge(notif)

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
