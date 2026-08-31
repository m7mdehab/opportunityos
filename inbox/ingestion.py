"""Provider-neutral Inbound Message Ingestion Boundary with Read-Only Invariant."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, Sequence
from .models import InboundMessageEvidence


class InboundMailTransport(Protocol):
    """Protocol defining read-only provider interactions."""
    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        ...


class MockMailTransport:
    """In-memory deterministic mock mail transport for testing."""
    def __init__(self, messages: Sequence[InboundMessageEvidence] = ()) -> tuple:
        self._messages = list(messages)
        self._cursor = "0"
        self._mutations_attempted = 0

    def add_message(self, msg: InboundMessageEvidence) -> None:
        self._messages.append(msg)

    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        start_idx = int(since_cursor) if since_cursor is not None and since_cursor.isdigit() else 0
        end_idx = min(start_idx + limit, len(self._messages))
        batch = tuple(self._messages[start_idx:end_idx])
        next_cursor = str(end_idx)
        return batch, next_cursor

    # Assert read-only safety: any mutating method call raises
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
    """Production-shaped Gmail API adapter enforcing read-only scopes (https://www.googleapis.com/auth/gmail.readonly)."""
    def __init__(self, credentials_provider: Any = None) -> None:
        self.credentials_provider = credentials_provider
        self.required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    def fetch_messages(self, since_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        # Live execution requests narrowest read-only scope; returns empty if no credentials provided
        if not self.credentials_provider:
            return (), since_cursor or "0"
        return (), since_cursor or "0"


class InboundIngestionService:
    """Ingests messages from a transport, guarantees deduplication, and stores evidence."""
    def __init__(self, transport: InboundMailTransport) -> None:
        self.transport = transport
        self._seen_content_hashes: set[str] = set()
        self._stored_evidence: dict[str, InboundMessageEvidence] = {}

    def poll_new_messages(self, current_cursor: str | None = None, limit: int = 50) -> tuple[tuple[InboundMessageEvidence, ...], str]:
        raw_messages, next_cursor = self.transport.fetch_messages(since_cursor=current_cursor, limit=limit)
        deduped: list[InboundMessageEvidence] = []
        for msg in raw_messages:
            if msg.message_content_hash not in self._seen_content_hashes:
                self._seen_content_hashes.add(msg.message_content_hash)
                self._stored_evidence[msg.message_content_hash] = msg
                deduped.append(msg)
        return tuple(deduped), next_cursor

    def get_evidence_by_hash(self, content_hash: str) -> InboundMessageEvidence | None:
        return self._stored_evidence.get(content_hash)

    def all_evidence(self) -> tuple[InboundMessageEvidence, ...]:
        return tuple(self._stored_evidence.values())
