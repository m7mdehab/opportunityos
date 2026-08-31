"""Unit tests for Inbound Message Ingestion Boundary."""
import unittest
from .fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES
from .ingestion import InboundIngestionService, MockMailTransport


class TestInboxIngestion(unittest.TestCase):
    def test_read_only_inbound_ingestion_and_deduplication(self) -> None:
        transport = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)
        service = InboundIngestionService(transport)

        # First poll: ingests all 6
        msgs, next_cur = service.poll_new_messages()
        self.assertEqual(len(msgs), 6)
        self.assertEqual(next_cur, "6")

        # Second poll: transport has no new messages
        msgs2, next_cur2 = service.poll_new_messages(current_cursor=next_cur)
        self.assertEqual(len(msgs2), 0)

        # Replay same messages: deduplication guarantees 0 duplicate stored evidence
        transport2 = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)
        service2 = InboundIngestionService(transport2)
        m_a, _ = service2.poll_new_messages()
        m_b, _ = service2.poll_new_messages(current_cursor="0")
        self.assertEqual(len(m_a), 6)
        self.assertEqual(len(m_b), 0)

    def test_mailbox_mutation_strictly_prohibited(self) -> None:
        transport = MockMailTransport()
        with self.assertRaises(PermissionError):
            transport.send_message()
        with self.assertRaises(PermissionError):
            transport.delete_message()
        with self.assertRaises(PermissionError):
            transport.mark_read()
        with self.assertRaises(PermissionError):
            transport.archive_message()
        self.assertEqual(transport._mutations_attempted, 4)


if __name__ == "__main__":
    unittest.main()
