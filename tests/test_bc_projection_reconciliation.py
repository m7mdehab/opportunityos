from __future__ import annotations

import unittest

from scripts.refresh_feed_projection_candidates import (
    MAX_CANDIDATES,
    _parse_args,
    summarize_reconciliation_states,
)


class BCProjectionReconciliationTests(unittest.TestCase):
    def test_current_for_you_reconciliation_is_bounded(self) -> None:
        self.assertEqual(MAX_CANDIDATES, 200)
        args, ids = _parse_args([
            "--reconcile-current-for-you",
            "--candidate-limit",
            "200",
        ])
        self.assertTrue(args.reconcile_current_for_you)
        self.assertFalse(args.execute)
        self.assertEqual(ids, ())

    def test_reconciliation_summary_keeps_recommended_and_suppressed_counts(self) -> None:
        self.assertEqual(
            summarize_reconciliation_states(
                {"for_you": 6, "review": 40, "excluded": 106},
                expected_count=152,
            ),
            {
                "for_you": 6,
                "review": 40,
                "excluded": 106,
                "suppressed_from_for_you": 146,
            },
        )

    def test_reconciliation_rejects_incomplete_or_unknown_projection_states(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid or incomplete"):
            summarize_reconciliation_states({"for_you": 1, "pending": 1}, expected_count=2)
        with self.assertRaisesRegex(ValueError, "invalid or incomplete"):
            summarize_reconciliation_states({"for_you": 1}, expected_count=2)

    def test_reconciliation_parser_rejects_a_corpus_wide_limit(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args([
                "--reconcile-current-for-you",
                "--candidate-limit",
                str(MAX_CANDIDATES + 1),
            ])


if __name__ == "__main__":
    unittest.main()
