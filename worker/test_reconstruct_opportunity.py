"""BRIEF-FR-006 A1 defect regression test: worker.handlers._reconstruct_opportunity
must round-trip every A1M founder-control column, not just avoid raising.

Uses SQLite (matching worker/test_reextract_all.py's convention) -- this exercises
`_reconstruct_opportunity`'s own column-reading logic, not PostgreSQL-specific
behavior, so no Postgres DSN is required here.
"""
import json
import os
import tempfile
import unittest

from storage.engine import get_engine, get_session_factory, init_db
from storage.models import OpportunityRecord
from worker.handlers import _reconstruct_opportunity
from opportunity.models import RemoteScope, WorkMode


class TestReconstructOpportunityRoundTrip(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_reconstruct.db")
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session = get_session_factory(self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_all_seven_a1_fields_and_compensation_survive_reconstruction(self) -> None:
        record = OpportunityRecord(
            id="opp-roundtrip-1",
            track="employment",
            title="Senior Backend Engineer",
            organization="Acme",
            description="Fully remote role, Egypt-friendly, region-restricted to EG/SA.",
            source_id="himalayas",
            source_url="https://himalayas.app/jobs/opp-roundtrip-1",
            content_hash="hash-roundtrip-1",
            work_mode="hybrid",
            work_mode_source="adapter",
            location_country="EG",
            location_city="Cairo",
            location_region="MENA",
            remote_scope="region_restricted",
            remote_scope_regions=json.dumps(["EG", "SA"]),
            compensation_min=100000,
            compensation_max=150000,
            compensation_currency="USD",
            compensation_period="yearly",
        )
        self.session.add(record)
        self.session.commit()

        opp = _reconstruct_opportunity(self.session, record)

        self.assertEqual(WorkMode.HYBRID, opp.work_mode)
        self.assertEqual("adapter", opp.work_mode_source)
        self.assertEqual("EG", opp.location_country)
        self.assertEqual("Cairo", opp.location_city)
        self.assertEqual("MENA", opp.location_region)
        self.assertEqual(RemoteScope.REGION_RESTRICTED, opp.remote_scope)
        self.assertEqual(("EG", "SA"), opp.remote_scope_regions)
        self.assertIsNotNone(opp.compensation)
        self.assertEqual(100000.0, opp.compensation.min_amount)
        self.assertEqual(150000.0, opp.compensation.max_amount)
        self.assertEqual("USD", opp.compensation.currency)
        self.assertEqual("yearly", opp.compensation.interval.value)
        # remote_policy is the read-only derived alias -- must agree with work_mode.
        from opportunity.models import RemotePolicy
        self.assertEqual(RemotePolicy.HYBRID, opp.remote_policy)

    def test_unbackfilled_row_falls_back_to_legacy_remote_policy_provenance(self) -> None:
        """A row written before this brief's adapters: work_mode is still at its
        migration default ("unspecified") because reextract_all has not backfilled
        it yet, but a legacy field_provenances row named "remote_policy" (the old
        adapter code's provenance field name) survives. Reconstruction must use it
        rather than silently reporting UNSPECIFIED when better information exists.
        """
        from storage.models import FieldProvenanceRecord

        record = OpportunityRecord(
            id="opp-legacy-1",
            track="employment",
            title="Legacy Row Engineer",
            organization="OldCo",
            description="desc",
            source_id="remotive",
            source_url="https://remotive.com/opp-legacy-1",
            content_hash="hash-legacy-1",
            # work_mode/remote_scope left at their migration defaults (never backfilled).
        )
        self.session.add(record)
        self.session.commit()
        self.session.add(
            FieldProvenanceRecord(
                opportunity_id="opp-legacy-1",
                field_name="remote_policy",
                raw_value="Remote",
                normalized_value="remote",
                derivation_type="rule_derivation",
                raw_pointer="feed:jobs[0]",
                record_checksum="chk-legacy-1",
                rule_id="extract_remote_policy",
            )
        )
        self.session.commit()

        opp = _reconstruct_opportunity(self.session, record)

        self.assertEqual(WorkMode.REMOTE, opp.work_mode)

    def test_no_signal_at_all_reconstructs_unspecified_not_fabricated(self) -> None:
        record = OpportunityRecord(
            id="opp-blank-1",
            track="employment",
            title="Blank Row",
            organization="NoSignalCo",
            description="desc",
            source_id="remote_ok",
            source_url="https://remoteok.com/opp-blank-1",
            content_hash="hash-blank-1",
        )
        self.session.add(record)
        self.session.commit()

        opp = _reconstruct_opportunity(self.session, record)

        self.assertEqual(WorkMode.UNSPECIFIED, opp.work_mode)
        self.assertEqual("none", opp.work_mode_source)
        self.assertEqual("", opp.location_country)
        self.assertEqual(RemoteScope.UNSPECIFIED, opp.remote_scope)
        self.assertEqual((), opp.remote_scope_regions)
        self.assertIsNone(opp.compensation)


if __name__ == "__main__":
    unittest.main()
