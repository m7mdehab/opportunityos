"""Unit tests for Inbound Operational Models."""
import unittest
from .models import (
    ExtractedDeadline,
    InboundMessageEvidence,
    InboundSignal,
    SignalCategory,
    SignalPriority,
)
from matching.models import Track


class TestInboxModels(unittest.TestCase):
    def test_inbound_evidence_hashing(self) -> None:
        ev1 = InboundMessageEvidence(
            provider="gmail", provider_message_id="msg-1", thread_id="th-1",
            sender_email="recruiter@acme.com", sender_name="Acme",
            recipient_email="founder@example.com", subject="Interview Invitation",
            snippet="Hello", body_text="Hello, let's interview.", body_html="<p>Hello</p>",
            received_at="2026-08-30T10:00:00Z",
        )
        self.assertTrue(len(ev1.message_content_hash) == 64)

        ev2 = InboundMessageEvidence(
            provider="gmail", provider_message_id="msg-1", thread_id="th-1",
            sender_email="recruiter@acme.com", sender_name="Acme",
            recipient_email="founder@example.com", subject="Interview Invitation",
            snippet="Hello", body_text="Hello, let's interview.", body_html="<p>Hello</p>",
            received_at="2026-08-30T10:00:00Z",
        )
        self.assertEqual(ev1.message_content_hash, ev2.message_content_hash)


if __name__ == "__main__":
    unittest.main()
