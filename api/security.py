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
#: "testserver" is Starlette's TestClient default ASGI `scope["server"]` host,
#: and "testclient" is its default transport peer address; both are treated
#: as loopback so the `Secure` cookie flag behaves in tests exactly as it
#: does on a real localhost run.


def constant_time_password_check(candidate: str, expected: str) -> bool:
    """Compare a submitted password against the configured founder password
    in constant time. Never uses ``==`` on secret material."""
    if not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_localhost_bind(server: tuple[object, object] | None) -> bool:
    """Whether this connection was accepted on a loopback bind address, for
    the purpose of deciding the session cookie's ``Secure`` flag.

    Finding 3 (council, auth review): the previous version of this check
    read the client-supplied ``Host`` header, which a request can set to
    anything (``Host: localhost:8021`` from a non-local client produced a
    cookie with no ``Secure`` flag), and it failed *open* -- missing host
    information was treated as loopback. Both are wrong for a flag whose
    entire job is "only omit Secure when we are certain this is loopback."

    This instead reads ASGI ``scope["server"]`` -- the transport-reported
    local socket address the connection was actually accepted on, set by
    the server (uvicorn/Starlette), never by request content a client
    controls -- and inverts the missing-information default: unknown now
    means ``Secure`` is set, not omitted. ADR-0013 defers real cookie
    posture (TLS, ``Secure``, ``__Host-``) to FR-005; this only removes a
    spoofable, fail-open decision point before that boundary moves.
    """
    if not server:
        return False
    host = str(server[0]).split("%")[0].strip().lower()
    return host in _LOCALHOST_HOSTS


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
    """A best-effort, in-memory sliding-window rate limiter over a single,
    global budget -- not per-client.

    Finding 2 (council, auth review): a limiter keyed by client address is
    trivially bypassable on loopback, because on loopback the *client*
    chooses its own source address -- any unprivileged local process can
    bind 127.0.0.2, 127.0.0.3, ... across all of 127.0.0.0/8 (and ::1) and
    get a fresh budget on every address, defeating the 5/min limit entirely.
    Demonstrated live: after exhausting 127.0.0.1, a request appearing to
    come from 127.0.0.2 was allowed immediately.

    This is a single-founder service (ADR-0012/ADR-0013): there is no
    legitimate second client to distinguish, so there is nothing lost --
    and a real attacker gained, per the finding above -- by keying on
    client identity at all. One global bucket closes the bypass and is
    simpler than what it replaces.

    Not durable across process restarts and not shared across processes --
    see ADR-0013 (a restart resets the budget; that is a known, accepted
    limitation of this alpha-grade posture, not something this fix changes).
    """

    max_attempts: int = LOGIN_RATE_LIMIT_ATTEMPTS
    window_seconds: float = LOGIN_RATE_LIMIT_WINDOW_SECONDS
    _attempts: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_record(self) -> int | None:
        """Record a login attempt against the single global budget. Returns
        ``None`` if allowed, or the number of seconds the caller must wait
        before retrying."""
        now = time.monotonic()
        with self._lock:
            attempts = [t for t in self._attempts if now - t < self.window_seconds]
            if len(attempts) >= self.max_attempts:
                oldest = min(attempts)
                retry_after = self.window_seconds - (now - oldest)
                self._attempts = attempts
                return max(1, int(retry_after) + 1)
            attempts.append(now)
            self._attempts = attempts
            return None

    def reset(self) -> None:
        with self._lock:
            self._attempts = []
