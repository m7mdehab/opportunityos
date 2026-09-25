from __future__ import annotations

import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from storage.models import Base, OpportunityRecord
from storage.reevaluation_batch import (
    DEFAULT_REEVALUATION_BATCH_SIZE,
    MAX_REEVALUATION_BATCH_SIZE,
    select_reevaluation_batch,
)


class ReevaluationBatchSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    @staticmethod
    def _opportunity(opportunity_id: str, track: str = "employment") -> OpportunityRecord:
        return OpportunityRecord(
            id=opportunity_id,
            track=track,
            title=f"Synthetic role {opportunity_id}",
            organization="Synthetic organization",
            description="Synthetic description used only in temporary SQLite.",
            source_id="synthetic-test",
            source_url=f"https://example.invalid/{opportunity_id}",
            content_hash=(opportunity_id.encode("utf-8").hex() * 64)[:64],
        )

    def test_selects_ordered_employment_ids_with_one_row_lookahead(self) -> None:
        self.session.add_all([
            self._opportunity("job-c"),
            self._opportunity("job-a"),
            self._opportunity("job-b"),
            self._opportunity("independent-a", track="independent"),
        ])
        self.session.commit()

        first = select_reevaluation_batch(self.session, batch_size=2)
        second = select_reevaluation_batch(
            self.session,
            start_after=first.next_cursor,
            batch_size=2,
        )

        self.assertEqual(first.opportunity_ids, ("job-a", "job-b"))
        self.assertEqual(first.selected_count, 2)
        self.assertEqual(first.next_cursor, "job-b")
        self.assertTrue(first.has_more)
        self.assertEqual(second.opportunity_ids, ("job-c",))
        self.assertEqual(second.next_cursor, "job-c")
        self.assertFalse(second.has_more)

    def test_selector_returns_ids_only_and_does_not_mutate_rows(self) -> None:
        opportunity = self._opportunity("job-a")
        self.session.add(opportunity)
        self.session.commit()
        before_description = opportunity.description
        before_count = self.session.query(OpportunityRecord).count()

        batch = select_reevaluation_batch(self.session)

        self.assertEqual(batch.opportunity_ids, ("job-a",))
        self.assertFalse(self.session.new)
        self.assertFalse(self.session.dirty)
        self.assertFalse(self.session.deleted)
        self.assertEqual(self.session.query(OpportunityRecord).count(), before_count)
        self.assertEqual(opportunity.description, before_description)
        self.assertFalse(hasattr(batch, "description"))

    def test_database_query_selects_only_ids_and_is_limited(self) -> None:
        statements: list[str] = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
        )

        select_reevaluation_batch(self.session, batch_size=4)

        query = statements[-1].casefold()
        self.assertIn("select opportunities.id", query)
        self.assertIn("limit", query)
        self.assertNotIn("description", query)
        self.assertNotIn("raw_payload_json", query)

    def test_hard_maximum_caps_page_size_and_uses_one_lookahead_id(self) -> None:
        self.session.add_all([
            self._opportunity(f"job-{index:03d}") for index in range(MAX_REEVALUATION_BATCH_SIZE + 1)
        ])
        self.session.commit()

        batch = select_reevaluation_batch(self.session)

        self.assertEqual(batch.selected_count, MAX_REEVALUATION_BATCH_SIZE)
        self.assertEqual(batch.next_cursor, "job-099")
        self.assertTrue(batch.has_more)

    def test_empty_page_keeps_resume_cursor_and_reports_no_more_rows(self) -> None:
        batch = select_reevaluation_batch(self.session, start_after="job-z")
        self.assertEqual(batch.opportunity_ids, ())
        self.assertEqual(batch.next_cursor, "job-z")
        self.assertFalse(batch.has_more)

    def test_default_and_hard_maximum_are_100(self) -> None:
        self.assertEqual(DEFAULT_REEVALUATION_BATCH_SIZE, 100)
        self.assertEqual(MAX_REEVALUATION_BATCH_SIZE, 100)

    def test_rejects_boolean_non_integer_and_out_of_range_sizes(self) -> None:
        for invalid in (True, False, "10", 0, -1, MAX_REEVALUATION_BATCH_SIZE + 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    select_reevaluation_batch(self.session, batch_size=invalid)

    def test_rejects_invalid_cursor_values(self) -> None:
        for invalid in ("", " job-a", "job-a ", "x" * 65, "job\nA"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    select_reevaluation_batch(self.session, start_after=invalid)
        with self.assertRaises(TypeError):
            select_reevaluation_batch(self.session, start_after=10)


if __name__ == "__main__":
    unittest.main()
