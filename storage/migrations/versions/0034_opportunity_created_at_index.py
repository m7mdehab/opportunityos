"""index opportunity creation date for dashboard metrics

Revision ID: 0034_opportunity_created_at
Revises: 0033_hosted_feed_family_key
Create Date: 2026-09-29 03:58:07.561802

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0034_opportunity_created_at'
down_revision: Union[str, None] = '0033_hosted_feed_family_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dashboard metrics filter opportunities by creation date. Build
    # concurrently so index creation does not block opportunity writes.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_opportunities_created_at",
            "opportunities",
            ["created_at"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_opportunities_created_at",
            table_name="opportunities",
            postgresql_concurrently=True,
        )
