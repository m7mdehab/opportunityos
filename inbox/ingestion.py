"""Provider-neutral Inbound Message Ingestion Boundary with Read-Only Invariant and Durable Store."""
from __future__ import annotations

import base64
import email
from email import policy
import json
from typing import Any, Protocol, Sequence
from .models import InboundMessageEvidence
from .persistence import DurableInboxStore


class InboundMailTransport(Protocol):
    """Protocol defining read-only provider interactions."""
    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        ...


class MockMailTransport:
    """In-memory deterministic mock mail transport for testing."""
    def __init__(self, messages: Sequence[InboundMessageEvidence] = ()) -> None:
        self._messages = list(messages)
        self._cursor = "0"
        self._mutations_attempted = 0
        self.should_fail_fetch = False

    def add_message(self, msg: InboundMessageEvidence) -> None:
        self._messages.append(msg)

    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        if self.should_fail_fetch:
            raise ConnectionError("Transient network failure during mail fetch")
        start_idx = int(since_cursor) if since_cursor is not None and since_cursor.isdigit() else 0
        end_idx = min(start_idx + limit, len(self._messages))
        batch = tuple(self._messages[start_idx:end_idx])
        next_cursor = str(end_idx)
        return batch, next_cursor

    def send_message(self, *args: Any, **kwargs: Any) -> None:
        self._mutations_attempted += 1
        raise PermissionError("Mailbox mutation prohibited: send_message is not authorized under BRIEF-006")

    def delete_message(self, *args: Any, **kwargs: Any) -> None:
        self._mutations_attempted += 1
        raise PermissionError("Mailbox mutation prohibited: delete_message is not authorized under BRIEF-006")

    def mark_read(self, *args: Any, **kwargs: Any) -> None:
        self._mutations_attempted += 1
        raise PermissionError("Mailbox mutation prohibited: mark_read is not authorized under BRIEF-006")

    def archive_message(self, *args: Any, **kwargs: Any) -> None:
        self._mutations_attempted += 1
        raise PermissionError("Mailbox mutation prohibited: archive_message is not authorized under BRIEF-006")


class GmailReadOnlyAdapter:
    """Production-shaped Gmail API adapter enforcing read-only scopes."""
    def __init__(self, mock_client: Any = None) -> None:
        self.client = mock_client
        self.required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        if not self.client:
            return (), since_cursor or "0"
        
        resp = self.client.users().messages().list(userId="me", pageToken=since_cursor, maxResults=limit).execute()
        msg_stubs = resp.get("messages", [])
        next_token = resp.get("nextPageToken", since_cursor or "0")

        evidence_list: list[InboundMessageEvidence] = []
        for stub in msg_stubs:
            msg_id = stub.get("id")
            raw_msg = self.client.users().messages().get(userId="me", id=msg_id, format="full").execute()
            
            # Map Gmail payload structure
            headers_list = raw_msg.get("payload", {}).get("headers", [])
            headers_dict = {h["name"].lower(): h["value"] for h in headers_list}
            headers_tuple = tuple([(h["name"], h["value"]) for h in headers_list])

            subject = headers_dict.get("subject", "")
            sender = headers_dict.get("from", "")
            recipient = headers_dict.get("to", "")
            received_at = headers_dict.get("date", "2026-08-30T00:00:00Z")
            snippet = raw_msg.get("snippet", "")
            thread_id = raw_msg.get("threadId", msg_id)

            # Body parsing
            body_text = snippet
            parts = raw_msg.get("payload", {}).get("parts", [])
            attachment_names = []
            for part in parts:
                fn = part.get("filename")
                if fn:
                    attachment_names.append(fn)
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    try:
                        decoded = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        body_text = decoded
                    except Exception:
                        pass

            ev = InboundMessageEvidence(
                provider="gmail", provider_message_id=msg_id, thread_id=thread_id,
                sender_email=sender, sender_name=sender, recipient_email=recipient,
                subject=subject, snippet=snippet, body_text=body_text, body_html="",
                received_at=received_at, headers=headers_tuple,
                attachment_names=tuple(attachment_names),
            )
            evidence_list.append(ev)

        return tuple(evidence_list), str(next_token)


class InboundIngestionService:
    """Ingests messages from a transport, guarantees durable deduplication and persistence."""
    def __init__(self, transport: InboundMailTransport, store: DurableInboxStore | None = None) -> None:
        self.transport = transport
        self.store = store or DurableInboxStore(":memory:")

    def poll_new_messages(self, current_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        raw_messages, next_cursor = self.transport.fetch_messages(since_cursor=current_cursor, limit=limit)
        deduped: list[InboundMessageEvidence] = []
        for msg in raw_messages:
            existing = self.store.get_evidence(msg.message_content_hash)
            if not existing:
                self.store.store_evidence(msg)
                deduped.append(msg)
        return tuple(deduped), next_cursor

    def get_evidence_by_hash(self, content_hash: str) -> InboundMessageEvidence | None:
        return self.store.get_evidence(content_hash)

    def all_evidence(self) -> tuple[InboundMessageEvidence, ...]:
        return self.store.get_all_evidence()
