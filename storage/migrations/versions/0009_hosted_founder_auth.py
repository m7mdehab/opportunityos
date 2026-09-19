"""Durable single-Founder authentication state."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_hosted_founder_auth"
down_revision: Union[str, None] = "0008_artifact_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D3_FILTER_SEED_OVERRIDES: dict[str, str] = {}


def upgrade() -> None:
    op.create_table(
        "founder_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("auth_version", sa.String(16), nullable=False, server_default="v1"),
    )
    op.create_index("ix_founder_sessions_token_digest", "founder_sessions", ["token_digest"], unique=True)
    op.create_index("ix_founder_sessions_expires_at", "founder_sessions", ["expires_at"])
    op.create_index("ix_founder_sessions_revoked_at", "founder_sessions", ["revoked_at"])
    op.create_table(
        "founder_auth_rate_limit",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "founder_auth_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.Column("session_id", sa.String(64)),
    )
    op.create_index("ix_founder_auth_events_event_type", "founder_auth_events", ["event_type"])
    op.create_index("ix_founder_auth_events_created_at", "founder_auth_events", ["created_at"])
    op.create_index("ix_founder_auth_events_request_id", "founder_auth_events", ["request_id"])
    op.create_index("ix_founder_auth_events_session_id", "founder_auth_events", ["session_id"])
    from storage.rls_policy import apply_postgres_deny_policies
    if op.get_bind().dialect.name == "postgresql":
        apply_postgres_deny_policies(op)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        from storage.rls_policy import remove_postgres_deny_policies
        remove_postgres_deny_policies(op)
    op.drop_table("founder_auth_events")
    op.drop_table("founder_auth_rate_limit")
    op.drop_table("founder_sessions")
