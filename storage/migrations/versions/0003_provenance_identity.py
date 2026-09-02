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
import json
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_provenance_identity'
down_revision: Union[str, None] = '0002_match_evaluations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- D3: founder_filter_settings seed data -----------------------------------
# The ten filters and their defaults, verbatim from
# reports/evidence/FR-005/d3-contract.md section 3. ``api/filters.py``'s
# ``FILTER_DEFINITIONS`` is the runtime source of truth the API falls back to
# if a row is ever missing; this tuple is a deliberate, independent literal
# copy, not an import of application code, because a migration must keep
# producing the exact same schema forever even if a later commit changes
# ``api/filters.py``'s defaults. ``api/test_api.py`` asserts the two stay in
# sync today.
_D3_FILTER_SEED: tuple[tuple[str, bool, str, dict], ...] = (
    ("geo_eligibility", True, "label_only", {}),
    ("work_mode_onsite", True, "label_only", {}),
    ("red_lines", True, "hide", {}),
    ("excluded_industries", True, "hide", {}),
    ("track_preference", True, "rank_only", {}),
    ("target_roles", True, "rank_only", {}),
    ("premium_fulltime_onsite", True, "rank_only", {}),
    ("stale_postings", True, "label_only", {}),
    ("min_fit_score", False, "hide", {"min_score": 0}),
    ("compensation_floor", False, "rank_only", {"floor": 0, "currency": None}),
)


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
    op.create_table(
        'founder_filter_settings',
        sa.Column('filter_id', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('filter_id'),
    )

    # Seed all ten filters so a fresh database behaves correctly with no API
    # call (contract section 3). ``updated_at`` is written as an already-UTC,
    # tzinfo-stripped value -- see the timezone hazard note in
    # storage/models.py::FounderFilterSettingRecord -- so nothing here is
    # subject to the session ``timezone`` GUC converting an aware value before
    # storing it naive.
    filter_settings_table = sa.table(
        'founder_filter_settings',
        sa.column('filter_id', sa.String),
        sa.column('enabled', sa.Boolean),
        sa.column('mode', sa.String),
        sa.column('params_json', sa.Text),
        sa.column('updated_at', sa.DateTime),
    )
    seeded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    op.bulk_insert(
        filter_settings_table,
        [
            {
                'filter_id': filter_id,
                'enabled': enabled,
                'mode': mode,
                'params_json': json.dumps(params),
                'updated_at': seeded_at,
            }
            for filter_id, enabled, mode, params in _D3_FILTER_SEED
        ],
    )
    # --- end D3 block ----------------------------------------------------------


def downgrade() -> None:
    # --- D3: drop founder_filter_settings here (reverse order of upgrade) -----
    op.drop_table('founder_filter_settings')
    # --- end D3 block ----------------------------------------------------------

    # --- D5: field_provenances natural-identity constraint -----------------
    op.drop_constraint('uq_field_provenances_identity', 'field_provenances', type_='unique')
    # --- end D5 block --------------------------------------------------------
