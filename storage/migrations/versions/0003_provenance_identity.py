"""0003_provenance_identity

Revision ID: 0003_provenance_identity
Revises: 0002_match_evaluations
Create Date: 2026-09-03 00:00:00.000000

D5 -- give ``field_provenances`` a natural identity so a re-poll cannot
silently accumulate duplicate provenance rows for the same opportunity
field. The brief's own text names ``(opportunity_id, field_name,
source_locator)`` but there is no ``source_locator`` column; the closest
analogue, ``raw_pointer``, is nullable and therefore unusable in a
PostgreSQL unique constraint (NULLs never collide, so duplicates would
still be admitted). The verified-unique tuple actually used here is
``(opportunity_id, field_name, record_checksum)`` -- all three columns are
NOT NULL today, and a real ``persist_batch`` run through the ``himalayas``
fixture (including a mutated re-poll under the same identity) produced no
collisions on this tuple.

The surrogate autoincrement ``id`` stays the primary key: SQLAlchemy's
``Session.merge()`` (``storage/repository.py``) needs a stable PK to target,
and the unique constraint below is what actually gives the row its natural
identity.

D3 (founder-controlled filters) shares this revision file -- its
``founder_filter_settings`` table is added in the clearly marked block
below, independent of the provenance work.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_provenance_identity'
down_revision: Union[str, None] = '0002_match_evaluations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- D5: field_provenances natural-identity constraint -----------------
    # De-duplicate existing rows first so this migration never explodes on a
    # database that already has duplicates on the target tuple: keep the
    # lowest ``id`` per (opportunity_id, field_name, record_checksum) and
    # delete the rest.
    op.execute(
        """
        DELETE FROM field_provenances fp
        USING field_provenances fp_keep
        WHERE fp.opportunity_id = fp_keep.opportunity_id
          AND fp.field_name = fp_keep.field_name
          AND fp.record_checksum = fp_keep.record_checksum
          AND fp.id > fp_keep.id
        """
    )

    op.create_unique_constraint(
        'uq_field_provenances_identity',
        'field_provenances',
        ['opportunity_id', 'field_name', 'record_checksum'],
    )
    # --- end D5 block --------------------------------------------------------

    # --- D3: founder_filter_settings table goes here --------------------------
    # (left intentionally empty for D3 to fill in on this same revision)
    # --- end D3 block ----------------------------------------------------------


def downgrade() -> None:
    # --- D3: drop founder_filter_settings here (reverse order of upgrade) -----
    # (left intentionally empty for D3 to fill in on this same revision)
    # --- end D3 block ----------------------------------------------------------

    # --- D5: field_provenances natural-identity constraint -----------------
    op.drop_constraint('uq_field_provenances_identity', 'field_provenances', type_='unique')
    # --- end D5 block --------------------------------------------------------
