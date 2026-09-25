"""0015_fr008_tracker_foundation

Additive FR-008 persistence foundation for private tracker state, timeline,
application metadata, notes, reminders, interviews, document links, and cold
job snapshots. Existing state values and rows are left unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_fr008_tracker_foundation"
down_revision: Union[str, None] = "0014_backup_heartbeat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVATE_TRACKER_TABLES = (
    "founder_activity_events",
    "founder_application_details",
    "founder_tracker_notes",
    "founder_follow_ups",
    "founder_interviews",
    "founder_tracker_documents",
    "founder_tracker_snapshots",
)


def _protect_private_tracker_tables() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _PRIVATE_TRACKER_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
        for role in ("anon", "authenticated"):
            policy = f"{table}_browser_deny_{role}"
            op.execute(
                f"""DO $$ BEGIN
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'REVOKE ALL ON TABLE public.{table} FROM {role}';
                    EXECUTE 'CREATE POLICY {policy} ON public.{table} '
                         || 'FOR ALL TO {role} USING (false) WITH CHECK (false)';
                  END IF;
                END $$"""
            )


def _install_activity_append_only_trigger() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """CREATE FUNCTION public.opos_reject_founder_activity_event_mutation()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
             RAISE EXCEPTION 'founder_activity_events is append-only';
           END;
           $$"""
    )
    op.execute(
        """CREATE TRIGGER founder_activity_events_append_only
           BEFORE UPDATE OR DELETE ON public.founder_activity_events
           FOR EACH ROW EXECUTE FUNCTION public.opos_reject_founder_activity_event_mutation()"""
    )


def upgrade() -> None:
    op.add_column("founder_triage_states", sa.Column("saved_at", sa.DateTime(), nullable=True))
    op.add_column("founder_triage_states", sa.Column("applied_at", sa.DateTime(), nullable=True))
    op.add_column("founder_triage_states", sa.Column("closed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_founder_triage_states_saved_at", "founder_triage_states", ["saved_at"])
    op.create_index("ix_founder_triage_states_applied_at", "founder_triage_states", ["applied_at"])
    op.create_index("ix_founder_triage_states_closed_at", "founder_triage_states", ["closed_at"])
    op.create_index(
        "ix_founder_triage_states_state_updated_at",
        "founder_triage_states",
        ["state", sa.text("updated_at DESC")],
    )

    op.create_table(
        "founder_activity_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_founder_activity_events_idempotency_key"),
    )
    op.create_index(
        "ix_founder_activity_events_opportunity_event_at",
        "founder_activity_events",
        ["opportunity_id", sa.text("event_at DESC")],
    )

    op.create_table(
        "founder_tracker_notes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_founder_tracker_notes_opportunity_created_at",
        "founder_tracker_notes",
        ["opportunity_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "founder_follow_ups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_founder_follow_ups_opportunity_due_completed",
        "founder_follow_ups",
        ["opportunity_id", "due_at", "completed_at"],
    )

    op.create_table(
        "founder_interviews",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("round_label", sa.String(length=64), nullable=True),
        sa.Column("interview_type", sa.String(length=32), nullable=True),
        sa.Column("interview_format", sa.String(length=24), nullable=True),
        sa.Column("interviewer_name", sa.String(length=128), nullable=True),
        sa.Column("preparation_notes", sa.Text(), nullable=True),
        sa.Column("post_interview_notes", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_founder_interviews_opportunity_scheduled_at",
        "founder_interviews",
        ["opportunity_id", "scheduled_at"],
    )

    op.create_table(
        "founder_tracker_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("document_kind", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id", "document_kind", "document_id",
            name="uq_founder_tracker_documents_opportunity_kind_document",
        ),
    )
    op.create_index(
        "ix_founder_tracker_documents_opportunity_kind",
        "founder_tracker_documents",
        ["opportunity_id", "document_kind"],
    )

    op.create_table(
        "founder_application_details",
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("application_method", sa.String(length=32), nullable=True),
        sa.Column("application_reference", sa.String(length=256), nullable=True),
        sa.Column("selected_cv_document_id", sa.String(length=128), nullable=True),
        sa.Column("selected_cover_letter_document_id", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )

    op.create_table(
        "founder_tracker_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_cache_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=False),
        sa.Column("track", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("posted_date", sa.String(length=64), nullable=True),
        sa.Column("work_mode", sa.String(length=16), nullable=False),
        sa.Column("location_country", sa.String(length=2), nullable=True),
        sa.Column("location_city", sa.String(length=128), nullable=True),
        sa.Column("location_region", sa.Text(), nullable=True),
        sa.Column("remote_scope", sa.String(length=24), nullable=True),
        sa.Column("qualification_decision", sa.String(length=32), nullable=True),
        sa.Column("fit_score", sa.Float(), nullable=True),
        sa.Column("preference_score", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("truth_pack_hash", sa.String(length=64), nullable=True),
        sa.Column("selected_cv_document_id", sa.String(length=128), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_cache_key"], ["artifact_cache.cache_key"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id", "content_hash",
            name="uq_founder_tracker_snapshots_opportunity_content_hash",
        ),
    )
    op.create_index(
        "ix_founder_tracker_snapshots_opportunity_captured_at",
        "founder_tracker_snapshots",
        ["opportunity_id", sa.text("captured_at DESC")],
    )
    op.create_index(
        "ix_founder_tracker_snapshots_content_hash",
        "founder_tracker_snapshots",
        ["content_hash"],
    )

    _protect_private_tracker_tables()
    _install_activity_append_only_trigger()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS founder_activity_events_append_only ON public.founder_activity_events")
        op.execute("DROP FUNCTION IF EXISTS public.opos_reject_founder_activity_event_mutation()")
        for table in reversed(_PRIVATE_TRACKER_TABLES):
            for role in ("anon", "authenticated"):
                op.execute(f"DROP POLICY IF EXISTS {table}_browser_deny_{role} ON public.{table}")
            op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_founder_tracker_snapshots_content_hash", table_name="founder_tracker_snapshots")
    op.drop_index("ix_founder_tracker_snapshots_opportunity_captured_at", table_name="founder_tracker_snapshots")
    op.drop_table("founder_tracker_snapshots")
    op.drop_table("founder_application_details")
    op.drop_index("ix_founder_tracker_documents_opportunity_kind", table_name="founder_tracker_documents")
    op.drop_table("founder_tracker_documents")
    op.drop_index("ix_founder_interviews_opportunity_scheduled_at", table_name="founder_interviews")
    op.drop_table("founder_interviews")
    op.drop_index("ix_founder_follow_ups_opportunity_due_completed", table_name="founder_follow_ups")
    op.drop_table("founder_follow_ups")
    op.drop_index("ix_founder_tracker_notes_opportunity_created_at", table_name="founder_tracker_notes")
    op.drop_table("founder_tracker_notes")
    op.drop_index("ix_founder_activity_events_opportunity_event_at", table_name="founder_activity_events")
    op.drop_table("founder_activity_events")
    op.drop_index("ix_founder_triage_states_state_updated_at", table_name="founder_triage_states")
    op.drop_index("ix_founder_triage_states_closed_at", table_name="founder_triage_states")
    op.drop_index("ix_founder_triage_states_applied_at", table_name="founder_triage_states")
    op.drop_index("ix_founder_triage_states_saved_at", table_name="founder_triage_states")
    op.drop_column("founder_triage_states", "closed_at")
    op.drop_column("founder_triage_states", "applied_at")
    op.drop_column("founder_triage_states", "saved_at")
