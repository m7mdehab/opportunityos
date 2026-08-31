"""Unit tests for Dual-Track Response Classifier."""
import unittest
from .classifier import ResponseClassifier
from .fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES, GOLD_INDEPENDENT_MESSAGES
from .models import SignalCategory, SignalPriority


class TestResponseClassifier(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = ResponseClassifier()

    def test_gold_employment_messages_100_percent_recall(self) -> None:
        expected_cats = [
            SignalCategory.APPLICATION_CONFIRMATION,
            SignalCategory.REJECTION,
            SignalCategory.RECRUITER_OUTREACH,
            SignalCategory.INTERVIEW_REQUEST,
            SignalCategory.ASSESSMENT,
            SignalCategory.OFFER,
        ]
        for msg, exp in zip(GOLD_EMPLOYMENT_MESSAGES, expected_cats):
            sig = self.classifier.classify(msg)
            self.assertEqual(sig.category, exp)

    def test_gold_independent_messages_recall(self) -> None:
        expected_cats = [
            SignalCategory.PROPOSAL_CONFIRMATION,
            SignalCategory.CLARIFICATION_REQUEST,
            SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST,
            SignalCategory.AWARD_OR_WIN,
        ]
        for msg, exp in zip(GOLD_INDEPENDENT_MESSAGES, expected_cats):
            sig = self.classifier.classify(msg)
            self.assertEqual(sig.category, exp)

    def test_high_priority_signals_flag_founder_action(self) -> None:
        int_msg = GOLD_EMPLOYMENT_MESSAGES[3]  # Interview
        sig = self.classifier.classify(int_msg)
        self.assertEqual(sig.priority, SignalPriority.URGENT)
        self.assertTrue(sig.requires_founder_action)
        self.assertIsNotNone(sig.deadline)


if __name__ == "__main__":
    unittest.main()
