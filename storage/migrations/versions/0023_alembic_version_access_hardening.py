"""Keep Alembic migration control state inaccessible to browser roles."""
from typing import Sequence, Union

from alembic import op

revision: str = "0023_alembic_version_access_hardening"
down_revision: Union[str, None] = "0022_storage_v2_direct_tiering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # REVOKE PUBLIC as well as the explicit Supabase API roles: privileges
    # inherited from PUBLIC otherwise remain effective after named revokes.
    op.execute("REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC")
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM anon';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM authenticated';
          END IF;
        END $$"""
    )
    # No policy is created: browser roles have no table privileges, and RLS
    # remains a second deny-by-default boundary. Do not FORCE RLS; the table
    # owner/Alembic administrator must retain its implicit owner access.
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # This is a security hardening correction. Keep it in force on downgrade;
    # Alembic's owning role retains access and can still update version_num.
    pass
