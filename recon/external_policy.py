"""Pure allowlist for externally observable source-reconnaissance operations."""
from __future__ import annotations

from urllib.parse import urlparse


READ_ONLY_QUERY = "READ_ONLY_QUERY"


def permits(method: str, url: str, classification: str) -> bool:
    """Return whether this exact non-mutating operation is permitted."""
    parsed = urlparse(url)
    normalized_method = method.upper()
    if normalized_method in {"PUT", "PATCH", "DELETE"}:
        return False
    return (
        normalized_method == "POST"
        and classification == READ_ONLY_QUERY
        and parsed.scheme == "https"
        and parsed.hostname == "api.ted.europa.eu"
        and parsed.path == "/v3/notices/search"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )
