"""0008_artifact_storage: durable external artifact metadata."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_artifact_storage"
down_revision: Union[str, None] = "0007_source_schedules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artifact_cache", sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="postgres_payload"))
    op.add_column("artifact_cache", sa.Column("object_key", sa.String(length=256), nullable=True))
    op.add_column("artifact_cache", sa.Column("payload_sha256", sa.String(length=64), nullable=True))
    op.add_column("artifact_cache", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("artifact_cache", sa.Column("generation_version", sa.String(length=64), nullable=True))
    op.execute("UPDATE artifact_cache SET size_bytes = octet_length(payload) WHERE payload IS NOT NULL")
    op.alter_column("artifact_cache", "storage_backend", server_default=None)


def downgrade() -> None:
    for name in ("generation_version", "size_bytes", "payload_sha256", "object_key", "storage_backend"):
        op.drop_column("artifact_cache", name)
