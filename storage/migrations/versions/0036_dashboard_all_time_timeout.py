"""Allow exact all-time dashboard aggregation on the production corpus.

Revision ID: 0036_dashboard_all_time_timeout
Revises: 0035_dashboard_hidden_fastpath
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0036_dashboard_all_time_timeout"
down_revision: Union[str, None] = "0035_dashboard_hidden_fastpath"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Exact all-time totals scan several history tables. Keep the guard bounded,
    # while allowing the current ~31k-row hosted history to finish reliably.
    op.execute(
        "ALTER FUNCTION public.founder_dashboard_daily(integer, double precision) "
        "SET statement_timeout = '15s'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER FUNCTION public.founder_dashboard_daily(integer, double precision) "
        "RESET statement_timeout"
    )
