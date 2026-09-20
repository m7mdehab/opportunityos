"""0014_backup_heartbeat

Durable sanitized backup heartbeat for FR-007 monitoring/soak evidence.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_backup_heartbeat"
down_revision: Union[str, None] = "0013_hosted_poll_now_cadence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.create_table(
        "backup_heartbeats",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("backup_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encryption", sa.Boolean(), nullable=False),
        sa.Column("destination_class", sa.String(64), nullable=False),
        sa.Column("database_snapshot_sha", sa.String(64), nullable=False),
        sa.Column("artifact_run_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("ALTER TABLE public.backup_heartbeats ENABLE ROW LEVEL SECURITY")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'CREATE POLICY backup_heartbeats_browser_deny_anon ON public.backup_heartbeats FOR ALL TO anon USING (false) WITH CHECK (false)';
        EXECUTE 'REVOKE ALL ON public.backup_heartbeats FROM anon';
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'CREATE POLICY backup_heartbeats_browser_deny_authenticated ON public.backup_heartbeats FOR ALL TO authenticated USING (false) WITH CHECK (false)';
        EXECUTE 'REVOKE ALL ON public.backup_heartbeats FROM authenticated';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON public.backup_heartbeats FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("backup_heartbeats")
