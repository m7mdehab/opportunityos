"""0016 capacity archive

Lossless compressed cold storage for derived/reconstructable opportunity
payloads.  The hot opportunity identity row remains in place so foreign keys,
deduplication and source identity continue to work.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_capacity_archive"
down_revision: Union[str, None] = "0019_activity_view_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunity_cold_archive",
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_zlib", sa.LargeBinary(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("archive_version", sa.String(length=16), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )
    op.create_index(
        "ix_opportunity_cold_archive_content_hash",
        "opportunity_cold_archive",
        ["content_hash"],
    )
    from storage.rls_policy import apply_postgres_deny_policy_for_table
    if op.get_bind().dialect.name == "postgresql":
        apply_postgres_deny_policy_for_table(op, "opportunity_cold_archive")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS opportunity_cold_archive_browser_deny_anon ON opportunity_cold_archive")
    op.execute("DROP POLICY IF EXISTS opportunity_cold_archive_browser_deny_authenticated ON opportunity_cold_archive")
    op.execute("ALTER TABLE opportunity_cold_archive DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_opportunity_cold_archive_content_hash", table_name="opportunity_cold_archive")
    op.drop_table("opportunity_cold_archive")

