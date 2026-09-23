from __future__ import annotations

from typing import Any


def classify_database_exception(exc: BaseException) -> tuple[str, str | None]:
    """Return an allowlisted failure category without returning driver text."""
    original: Any = getattr(exc, "orig", exc)
    diagnostic = getattr(original, "diag", None)
    sqlstate = getattr(original, "pgcode", None) or getattr(diagnostic, "sqlstate", None)
    if sqlstate == "28P01":
        return "authentication-rejected", sqlstate
    if sqlstate == "3D000":
        return "database-name-rejected", sqlstate
    if sqlstate == "28000":
        return "authorization-rejected", sqlstate

    # Driver messages are inspected only in memory and are never returned or logged.
    message = str(original).lower()
    categories = (
        ("authentication-rejected", ("password authentication failed", "authentication failed")),
        ("dns-resolution", (
            "could not translate host name", "name or service not known",
            "temporary failure in name resolution", "nodename nor servname provided",
        )),
        ("connection-timeout", (
            "connection timed out", "timeout expired", "connect timeout expired",
        )),
        ("connection-refused", ("connection refused",)),
        ("ssl-failure", (
            "ssl error", "ssl handshake", "certificate verify failed",
            "certificate has expired", "server does not support ssl",
        )),
        ("network-unreachable", ("network is unreachable", "no route to host")),
        ("database-name-rejected", ("database does not exist",)),
        ("authorization-rejected", ("role does not exist", "no pg_hba.conf entry")),
        ("server-disconnected", (
            "server closed the connection unexpectedly", "terminating connection",
        )),
    )
    for category, needles in categories:
        if any(needle in message for needle in needles):
            return category, sqlstate
    if "could not connect to server" in message or "connection to server" in message:
        return "connection-failed", sqlstate
    return type(original).__name__, sqlstate
