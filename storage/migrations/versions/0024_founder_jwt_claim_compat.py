"""Accept current PostgREST JSON claims as well as the legacy subject GUC."""
from typing import Sequence, Union

from alembic import op

revision: str = "0024_founder_jwt_claims"
down_revision: Union[str, None] = "0023_alembic_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgREST installs request.jwt.claims as a JSON object. Older PostgREST
    # versions also populated request.jwt.claim.sub; accept either form while
    # retaining fail-closed behavior for missing or non-Founder subjects.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.opos_is_founder()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT EXISTS (
            SELECT 1
            FROM public.founder_identity AS founder
            WHERE founder.id = 'singleton'
              AND founder.supabase_user_id = COALESCE(
                NULLIF(current_setting('request.jwt.claim.sub', true), ''),
                NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
              )
          )
        $$
        """
    )


def downgrade() -> None:
    # Keep the claim compatibility fix in place on downgrade; replacing it
    # with the legacy-only function would silently lock the Founder out.
    pass
