"""Transport-log guard for BRIEF-FR-006 E23.

AGENTS.md: "Stop on 403, 429 ... never work around, never retry in this session."
`TransportLog.record` enforces that in code: once a source_id has returned a blocking
status (403 or 429), any further `record()` call for that same source_id raises
instead of allowing a second request to be logged.
"""
from __future__ import annotations

BLOCKING_STATUSES = (403, 429)


class BlockedSourceRetryError(RuntimeError):
    """Raised when a source that already returned 403/429 is requested again in the same run."""


class TransportLog:
    def __init__(self) -> None:
        self._blocked: set[str] = set()
        self._requests: list[tuple[str, int | str | None]] = []

    def record(self, source_id: str, status: int | str | None) -> None:
        if source_id in self._blocked:
            raise BlockedSourceRetryError(
                f"Refusing to request '{source_id}' again: it already returned a blocking "
                f"status (403/429) earlier in this run."
            )
        self._requests.append((source_id, status))
        if status in BLOCKING_STATUSES:
            self._blocked.add(source_id)

    @property
    def blocked_sources(self) -> tuple[str, ...]:
        return tuple(sorted(self._blocked))

    @property
    def requests(self) -> tuple[tuple[str, int | str | None], ...]:
        return tuple(self._requests)
