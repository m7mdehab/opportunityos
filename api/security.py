"""Auth primitives: constant-time password compare, signed session cookies,
and an in-memory login rate limiter.

Nothing here logs the founder password or a session cookie value. Only
``core.logging`` structured fields (component, run_id, counts) are ever
emitted.
"""

from __future__ import annotations

import hmac
import threading
import time
from dataclasses import dataclass, field

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .settings import (
    LOGIN_RATE_LIMIT_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    SESSION_MAX_AGE_SECONDS,
    Settings,
)

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1", "testclient", "testserver"}
#: "testserver" is Starlette's TestClient default Host header, and "testclient"
#: is its default transport peer address; both are treated as loopback so the
#: `Secure` cookie flag behaves in tests exactly as it does on a real localhost run.


def constant_time_password_check(candidate: str, expected: str) -> bool:
    """Compare a submitted password against the configured founder password
    in constant time. Never uses ``==`` on secret material."""
    if not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_localhost_request(host: str | None) -> bool:
    """Whether a request's host (no port) should be treated as loopback,
    for the purpose of deciding the session cookie's ``Secure`` flag."""
    if not host:
        return True
    bare_host = host.split(":")[0].strip().lower()
    return bare_host in _LOCALHOST_HOSTS


def make_serializer(session_secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(session_secret, salt="oos-session")


def sign_session(serializer: URLSafeTimedSerializer) -> str:
    return serializer.dumps({"authenticated": True})


def verify_session(serializer: URLSafeTimedSerializer, token: str | None) -> bool:
    if not token:
        return False
    try:
        payload = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return bool(isinstance(payload, dict) and payload.get("authenticated") is True)


@dataclass
class LoginRateLimiter:
    """A best-effort, in-memory sliding-window rate limiter.

    Not durable across process restarts and not shared across processes --
    see ADR-0013. Keyed by client identity (typically remote host).
    """

    max_attempts: int = LOGIN_RATE_LIMIT_ATTEMPTS
    window_seconds: float = LOGIN_RATE_LIMIT_WINDOW_SECONDS
    _attempts: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_record(self, key: str) -> int | None:
        """Record an attempt for ``key``. Returns ``None`` if allowed, or the
        number of seconds the caller must wait before retrying."""
        now = time.monotonic()
        with self._lock:
            attempts = [t for t in self._attempts.get(key, ()) if now - t < self.window_seconds]
            if len(attempts) >= self.max_attempts:
                oldest = min(attempts)
                retry_after = self.window_seconds - (now - oldest)
                self._attempts[key] = attempts
                return max(1, int(retry_after) + 1)
            attempts.append(now)
            self._attempts[key] = attempts
            return None

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
