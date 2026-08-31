"""Unit tests for Inbound Message Ingestion Boundary and Gmail Adapter."""
import unittest
from unittest.mock import MagicMock
from inbox.fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES
from inbox.ingestion import GmailReadOnlyAdapter, InboundIngestionService, MockMailTransport
from inbox.persistence import DurableInboxStore


class TestInboxIngestion(unittest.TestCase):
    def test_read_only_inbound_ingestion_and_durable_deduplication(self) -> None:
        store = DurableInboxStore(":memory:")
        transport = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)
        service = InboundIngestionService(transport, store=store)

        # First poll: ingests all messages in gold set
        msgs, next_cur = service.poll_new_messages()
        self.assertEqual(len(msgs), len(GOLD_EMPLOYMENT_MESSAGES))
        self.assertEqual(next_cur, str(len(GOLD_EMPLOYMENT_MESSAGES)))

        # Mark all messages as processed
        for m in msgs:
            store.mark_evidence_processed(m.message_content_hash, "2026-08-30T10:00:00Z")

        # Second poll with same cursor: 0 new messages
        msgs2, next_cur2 = service.poll_new_messages(current_cursor=next_cur)
        self.assertEqual(len(msgs2), 0)

        # Replay from beginning: all are marked processed => 0 unprocessed messages returned
        transport2 = MockMailTransport(messages=GOLD_EMPLOYMENT_MESSAGES)
        service2 = InboundIngestionService(transport2, store=store)
        m_a, _ = service2.poll_new_messages(current_cursor="0")
        self.assertEqual(len(m_a), 0)

    def test_gmail_adapter_read_and_pagination_execution(self) -> None:
        mock_gmail = MagicMock()
        mock_gmail.users().messages().list().execute.return_value = {
            "messages": [{"id": "g-msg-1"}, {"id": "g-msg-2"}],
            "nextPageToken": "page-tok-2",
        }
        mock_gmail.users().messages().get().execute.side_effect = [
            {
                "id": "g-msg-1", "threadId": "th-g-1", "snippet": "Interview invite",
                "payload": {"headers": [{"name": "Subject", "value": "Interview"}, {"name": "From", "value": "recruiter@acme.com"}]},
            },
            {
                "id": "g-msg-2", "threadId": "th-g-2", "snippet": "Job Offer",
                "payload": {"headers": [{"name": "Subject", "value": "Offer"}, {"name": "From", "value": "hr@acme.com"}]},
            },
        ]

        adapter = GmailReadOnlyAdapter(mock_client=mock_gmail)
        evidence_list, next_token = adapter.fetch_messages(limit=2)
        self.assertEqual(len(evidence_list), 2)
        self.assertEqual(next_token, "page-tok-2")
        self.assertEqual(evidence_list[0].provider, "gmail")
        self.assertEqual(evidence_list[0].provider_message_id, "g-msg-1")
        self.assertEqual(evidence_list[1].provider_message_id, "g-msg-2")

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
