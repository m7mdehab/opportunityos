"""Storage V2 metadata and lean-read-model transition.

No source truth is deleted here.  The migration only adds resumable archive
metadata and removes the duplicate projection full-text index.  A later,
explicit maintenance phase uploads/verifies cold bytes before clearing the
legacy PostgreSQL payload.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_storage_v2"
down_revision: Union[str, None] = "0020_capacity_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("archive_object_key", sa.String(length=255), nullable=True))
    op.add_column("opportunities", sa.Column("archive_sha256", sa.String(length=64), nullable=True))
    op.add_column("opportunities", sa.Column("archive_state", sa.String(length=16), nullable=True))
    op.add_column("opportunity_cold_archive", sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="postgres_payload"))
    op.add_column("opportunity_cold_archive", sa.Column("object_key", sa.String(length=255), nullable=True))
    op.add_column("opportunity_cold_archive", sa.Column("compressed_size_bytes", sa.Integer(), nullable=True))
    op.alter_column("opportunity_cold_archive", "payload_zlib", nullable=True)
    op.create_index("ix_opportunity_cold_archive_object_key", "opportunity_cold_archive", ["object_key"])
    op.execute("DROP INDEX IF EXISTS ix_feed_projection_search_tsv")


def downgrade() -> None:
    op.drop_index("ix_opportunity_cold_archive_object_key", table_name="opportunity_cold_archive")
    op.alter_column("opportunity_cold_archive", "payload_zlib", nullable=False)
    op.drop_column("opportunity_cold_archive", "compressed_size_bytes")
    op.drop_column("opportunity_cold_archive", "object_key")
    op.drop_column("opportunity_cold_archive", "storage_backend")
    op.drop_column("opportunities", "archive_state")
    op.drop_column("opportunities", "archive_sha256")
    op.drop_column("opportunities", "archive_object_key")
