"""OpportunityOS database backup and restore.

SECURITY NOTE: the backup produced by ``dump_database`` is written as
**unencrypted** plain JSON. Encryption at rest is not implemented anywhere in
this script or its callers. As a direct consequence, requirement
``REQ-SEC-003`` (backup encryption at rest) remains **MISSING** in the
founder readiness matrix until a future brief adds it. Anyone handling a
backup file produced by this script is handling founder data in the clear.
"""
import os
import sys
import json
import argparse
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from alembic.config import Config
from alembic import command

from storage.engine import get_engine, get_session_factory
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

# Repository root, derived from this file's location (not the process CWD).
# Used to resolve alembic.ini itself AND (see _build_alembic_config) to make
# the script_location/version_locations options and the sys.path entry
# env.py needs absolute, since Alembic resolves relative ini options against
# the process's CWD, not the ini file's own directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"

# Serialises _upgrade_to_head()'s OPPORTUNITYOS_DB_URL environment-variable
# swap (see its docstring): that swap mutates process-global os.environ, so
# without this lock a second, concurrent call in another thread of the same
# process could observe or overwrite the wrong value mid-upgrade.
_RESTORE_ENV_LOCK = threading.Lock()


class BackupCompletenessError(RuntimeError):
    """Raised when the dump's covered tables and the ORM metadata's tables disagree.

    This guards against a model table being added without a corresponding
    dump/restore section (silent data loss on backup), and against a dump
    section naming a table that no longer exists in the metadata (silent
    data loss on restore).
    """


# Explicit mapping from each JSON section key in the dump to the database
# table it covers. This is the single source of truth the completeness
# check is measured against; it intentionally is NOT derived from the loop
# bodies below so that adding a new `data[...]` section without updating
# this map still gets caught.
DUMP_SECTION_TABLE_MAP = {
    "opportunities": "opportunities",
    "field_provenances": "field_provenances",
    "outbound_actions": "outbound_actions",
    "idempotency_reservations": "idempotency_reservations",
    "inbound_evidence": "inbound_evidence",
    "pipeline_events": "pipeline_events",
    "founder_notifications": "founder_notifications",
    "inbox_checkpoints": "inbox_checkpoints",
    "reconciliation_records": "reconciliation_records",
    "worker_jobs": "worker_jobs",
    "founder_feedback": "founder_feedback",
}


def _check_dump_completeness() -> None:
    """Raise BackupCompletenessError if DUMP_SECTION_TABLE_MAP and
    Base.metadata.sorted_tables disagree on the set of tables covered."""
    covered_tables = set(DUMP_SECTION_TABLE_MAP.values())
    model_tables = {table.name for table in Base.metadata.sorted_tables}

    missing_from_dump = model_tables - covered_tables
    unknown_in_dump = covered_tables - model_tables

    if missing_from_dump or unknown_in_dump:
        raise BackupCompletenessError(
            "Backup completeness check failed: "
            f"model tables missing from dump map: {sorted(missing_from_dump)}; "
            f"dump map tables not present in model metadata: {sorted(unknown_in_dump)}. "
            "Update DUMP_SECTION_TABLE_MAP (and the corresponding dump/restore "
            "sections) to keep the backup complete."
        )


def _check_dump_row_counts(session, data: dict) -> None:
    """Raise BackupCompletenessError if any DUMP_SECTION_TABLE_MAP section's
    row count disagrees with its table's actual row count in `session`.

    `_check_dump_completeness()` only proves the *set of tables* covered by
    DUMP_SECTION_TABLE_MAP matches Base.metadata; it says nothing about
    whether the per-table query loop below that map actually ran. Someone
    who adds a model table plus a map entry but forgets to write (or wire
    up) the loop would still pass that check while silently dropping every
    row of that table from the backup. Comparing row counts, in the same
    session/transaction the dump itself ran in, catches exactly that.
    """
    for section, table_name in DUMP_SECTION_TABLE_MAP.items():
        if section not in data:
            raise BackupCompletenessError(
                f"Backup completeness check failed: dump section '{section}' "
                f"(mapped to table '{table_name}') was never populated."
            )
        expected_count = len(data[section])
        actual_count = session.query(func.count()).select_from(Base.metadata.tables[table_name]).scalar()
        if expected_count != actual_count:
            raise BackupCompletenessError(
                f"Backup completeness check failed: dump section '{section}' "
                f"contains {expected_count} row(s) but table '{table_name}' has "
                f"{actual_count} row(s) in the same snapshot. A dump loop is out "
                "of sync with DUMP_SECTION_TABLE_MAP."
            )


def dump_database(db_url: str, output_file: str) -> int:
    _check_dump_completeness()

    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    session = session_factory()

    if engine.dialect.name == "postgresql":
        # Each table below is read with its own SELECT. Left at the default
        # READ COMMITTED isolation level, a write concurrent with the dump
        # could land between two of those SELECTs and produce a
        # foreign-key-inconsistent backup (e.g. a provenance row dumped for
        # an opportunity that a later SELECT in this same dump no longer
        # sees, or vice versa). Pinning the session's connection to
        # REPEATABLE READ before the first query gives the whole dump one
        # consistent snapshot. This must happen before any query executes,
        # so the session's connection is established with the isolation
        # level already in effect.
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})

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
                "id": prov.id, "opportunity_id": prov.opportunity_id, "field_name": prov.field_name,
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

    # Row-count completeness check, run in the same session/transaction the
    # dump itself used, before that transaction is closed out.
    _check_dump_row_counts(session, data)

    session.close()
    engine.dispose()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return len(data["opportunities"])


def _build_alembic_config(db_url: str) -> Config:
    """Build an Alembic Config whose script_location/version_locations are
    absolute, not resolved against the process's current working directory.

    alembic.ini's `script_location = storage/migrations` and
    `version_locations = storage/migrations/versions` are written relative to
    the repository root, but Alembic resolves relative paths found in the ini
    file against the process CWD, not the ini file's own directory. Called
    from any other CWD this either raises `CommandError: Path doesn't exist`,
    or -- worse -- silently resolves against an unrelated directory that
    happens to contain its own storage/migrations tree and runs the WRONG
    migration scripts. Setting both options to paths derived from REPO_ROOT,
    and ensuring REPO_ROOT is on sys.path so env.py's `from storage.models
    import Base` resolves regardless of CWD, makes this CWD-independent.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    migrations_dir = REPO_ROOT / "storage" / "migrations"
    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("version_locations", str(migrations_dir / "versions"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _upgrade_to_head(db_url: str) -> None:
    """Run the Alembic upgrade to head programmatically against db_url.

    storage/migrations/env.py reads OPPORTUNITYOS_DB_URL from the environment
    and, when present, OVERRIDES whatever sqlalchemy.url was set via
    `set_main_option` (see `db_url = os.environ.get("OPPORTUNITYOS_DB_URL",
    config.get_main_option("sqlalchemy.url"))` in that file). If this
    function is called to restore into a target URL that differs from
    whatever OPPORTUNITYOS_DB_URL currently holds (e.g. restoring into a
    second scratch database while the environment still points at the
    primary one), a naive `set_main_option("sqlalchemy.url", db_url)` would
    be silently overridden by env.py and the migration would run against the
    WRONG database. That is the central correctness risk of this function:
    getting it wrong means restore silently migrates data into place against
    one database while the schema is stamped on another.

    This function mutates process-global os.environ["OPPORTUNITYOS_DB_URL"]
    for the duration of the upgrade (see below) and is serialised with
    _RESTORE_ENV_LOCK as a result: it is NOT safe to call concurrently from
    multiple threads within one process -- a second, concurrent call (or any
    other in-process code resolving OPPORTUNITYOS_DB_URL, such as
    storage.engine.get_engine(None) on another thread) would otherwise race
    the env var and could be silently redirected to this call's target
    database mid-upgrade. Concurrent restores from separate *processes* are
    unaffected, since each process has its own environment.
    """
    with _RESTORE_ENV_LOCK:
        alembic_cfg = _build_alembic_config(db_url)

        # To make the target URL authoritative, OPPORTUNITYOS_DB_URL is set
        # to db_url for the duration of the upgrade (so env.py's override
        # resolves to the same URL we intend), and the previous value is
        # restored in a `finally` block so this function never leaks
        # environment state into the caller.
        had_env_override = "OPPORTUNITYOS_DB_URL" in os.environ
        previous_env_value = os.environ.get("OPPORTUNITYOS_DB_URL")
        os.environ["OPPORTUNITYOS_DB_URL"] = db_url
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            if had_env_override:
                os.environ["OPPORTUNITYOS_DB_URL"] = previous_env_value
            else:
                del os.environ["OPPORTUNITYOS_DB_URL"]


def _check_restore_completeness(data: dict) -> None:
    """Raise BackupCompletenessError unless `data`'s sections exactly match
    DUMP_SECTION_TABLE_MAP's keys.

    BackupCompletenessError's contract includes guarding "against a dump
    section naming a table that no longer exists in the metadata (silent
    data loss on restore)" -- but every load loop below reads via
    `data.get(section, [])`, so without this check a dump taken before a
    schema change (missing a section the current code expects) restores
    silently with those tables left empty, and a dump section this restore
    code no longer recognises is silently ignored rather than raising.
    """
    dump_sections = set(data.keys()) - {"timestamp"}
    expected_sections = set(DUMP_SECTION_TABLE_MAP.keys())
    if dump_sections != expected_sections:
        missing = expected_sections - dump_sections
        unknown = dump_sections - expected_sections
        raise BackupCompletenessError(
            "Restore completeness check failed: dump sections do not match "
            "the sections this restore code knows how to load. "
            f"missing from dump (would restore empty): {sorted(missing)}; "
            f"unknown in dump (would be silently ignored): {sorted(unknown)}. "
            "This dump likely predates a schema/format change; restoring it "
            "as-is would silently lose or ignore data."
        )


def restore_database(dump_file: str, db_url: str) -> None:
    with open(dump_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    _check_restore_completeness(data)
    _upgrade_to_head(db_url)

    engine = get_engine(db_url)
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
        # merge() (not add()): the provenance dump now includes the
        # autoincrement primary key `id`, so re-restoring the same dump into
        # an already-restored database upserts by identity instead of
        # inserting duplicate rows.
        prov = FieldProvenanceRecord(**prov_dict)
        session.merge(prov)

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
