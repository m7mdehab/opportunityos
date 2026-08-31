"""Unit tests for Dual-Track Response Classifier on Complete 23-Scenario Gold Set."""
import unittest
from inbox.classifier import ResponseClassifier
from inbox.fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES, GOLD_INDEPENDENT_MESSAGES
from inbox.models import SignalCategory, SignalPriority


class TestResponseClassifier(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = ResponseClassifier()

    def test_complete_gold_employment_messages_recall_and_precision(self) -> None:
        expected_cats = [
            SignalCategory.APPLICATION_CONFIRMATION,
            SignalCategory.REJECTION,
            SignalCategory.RECRUITER_OUTREACH,
            SignalCategory.INTERVIEW_REQUEST,
            SignalCategory.INTERVIEW_REQUEST,  # Reschedule
            SignalCategory.ASSESSMENT,
            SignalCategory.INFORMATION_REQUEST,
            SignalCategory.OFFER,
            SignalCategory.MARKETING,
            SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION,
            SignalCategory.UNCLASSIFIED,
        ]
        for msg, exp in zip(GOLD_EMPLOYMENT_MESSAGES, expected_cats):
            sig = self.classifier.classify(msg)
            self.assertEqual(sig.category, exp, f"Failed for subject: {msg.subject}")

    def test_complete_gold_independent_messages_recall_and_precision(self) -> None:
        expected_cats = [
            SignalCategory.PROPOSAL_CONFIRMATION,
            SignalCategory.CLIENT_OR_BUYER_RESPONSE,
            SignalCategory.CLARIFICATION_REQUEST,
            SignalCategory.SHORTLIST_OR_INVITATION,
            SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST,
            SignalCategory.PROPOSAL_REJECTION,
            SignalCategory.AWARD_OR_WIN,
            SignalCategory.CONTRACT_PROGRESS,
            SignalCategory.PROCUREMENT_AMENDMENT,
            SignalCategory.PROCUREMENT_DEADLINE_CHANGE,
            SignalCategory.MARKETING,
            SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION,
        ]
        for msg, exp in zip(GOLD_INDEPENDENT_MESSAGES, expected_cats):
            sig = self.classifier.classify(msg)
            self.assertEqual(sig.category, exp, f"Failed for subject: {msg.subject}")

    def test_high_priority_signals_flag_founder_action(self) -> None:
        int_msg = GOLD_EMPLOYMENT_MESSAGES[3]  # Interview
        sig = self.classifier.classify(int_msg)
        self.assertEqual(sig.priority, SignalPriority.URGENT)
        self.assertTrue(sig.requires_founder_action)
        self.assertIsNotNone(sig.deadline)


if __name__ == "__main__":
    unittest.main()
