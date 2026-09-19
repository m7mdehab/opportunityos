"""Auth primitives: constant-time password compare, signed session cookies,
and an in-memory login rate limiter.

Nothing here logs the founder password or a session cookie value. Only
``core.logging`` structured fields (component, run_id, counts) are ever
emitted.
"""

from __future__ import annotations

import hmac
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from storage.models import FounderAuthEventRecord, FounderAuthRateLimitRecord, FounderSessionRecord
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


SCRYPT_FORMAT = "scrypt$v1"
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 2**14, 8, 1, 32


def hash_founder_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    enc = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"{SCRYPT_FORMAT}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${enc(salt)}${enc(derived)}"


def verify_founder_password(password: str, encoded: str | None) -> bool:
    try:
        if not isinstance(password, str) or not encoded:
            return False
        parts = encoded.split("$")
        if len(parts) != 7 or "$".join(parts[:2]) != SCRYPT_FORMAT:
            return False
        _, _, n_raw, r_raw, p_raw, salt_raw, digest_raw = parts
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if n != SCRYPT_N or r != SCRYPT_R or p != SCRYPT_P:
            return False
        pad = lambda value: value + "=" * (-len(value) % 4)
        salt = base64.urlsafe_b64decode(pad(salt_raw))
        expected = base64.urlsafe_b64decode(pad(digest_raw))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, OSError):
        return False


def session_digest(token: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _audit(session, event_type: str, outcome: str, request_id: str | None = None, session_id: str | None = None) -> None:
    session.add(FounderAuthEventRecord(id=uuid.uuid4().hex, event_type=event_type, outcome=outcome,
                                       request_id=request_id, session_id=session_id,
                                       created_at=datetime.now(timezone.utc)))


def durable_rate_limit(session, *, now: datetime | None = None, max_attempts: int = LOGIN_RATE_LIMIT_ATTEMPTS,
                       window_seconds: int = LOGIN_RATE_LIMIT_WINDOW_SECONDS) -> int | None:
    now = now or datetime.now(timezone.utc)
    row = session.query(FounderAuthRateLimitRecord).filter_by(id="founder").with_for_update().one_or_none()
    if row is None:
        row = FounderAuthRateLimitRecord(id="founder", window_started_at=now, attempt_count=0, updated_at=now)
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            row = session.query(FounderAuthRateLimitRecord).filter_by(id="founder").with_for_update().one()
    if row.locked_until and row.locked_until > now:
        return max(1, int((row.locked_until - now).total_seconds()) + 1)
    window_started = row.window_started_at.replace(tzinfo=timezone.utc) if row.window_started_at.tzinfo is None else row.window_started_at
    if (now - window_started).total_seconds() >= window_seconds:
        row.window_started_at, row.attempt_count = now, 0
    if row.attempt_count >= max_attempts:
        row.locked_until = window_started + timedelta(seconds=window_seconds)
        return max(1, int((row.locked_until - now).total_seconds()) + 1)
    row.attempt_count += 1
    row.updated_at = now
    return None


def create_durable_session(session, secret: str, *, user_agent: str | None = None,
                           max_age: int = SESSION_MAX_AGE_SECONDS) -> tuple[str, FounderSessionRecord]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    row = FounderSessionRecord(id=uuid.uuid4().hex, token_digest=session_digest(token, secret),
                               created_at=now, expires_at=now + timedelta(seconds=max_age),
                               user_agent_hash=hashlib.sha256(user_agent.encode()).hexdigest() if user_agent else None)
    session.add(row)
    session.flush()
    return token, row


def get_durable_session(session, token: str | None, secret: str) -> FounderSessionRecord | None:
    if not token:
        return None
    row = session.query(FounderSessionRecord).filter_by(token_digest=session_digest(token, secret)).one_or_none()
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at.replace(tzinfo=timezone.utc) if row is not None and row.expires_at.tzinfo is None else (row.expires_at if row is not None else None)
    if row is None or row.revoked_at is not None or expires_at <= now:
        return None
    row.last_seen_at = now
    return row


def revoke_durable_session(session, token: str | None, secret: str) -> str | None:
    row = get_durable_session(session, token, secret)
    if row is not None:
        row.revoked_at = datetime.now(timezone.utc)
        return row.id
    return None


def revoke_all_durable_sessions(session) -> int:
    now = datetime.now(timezone.utc)
    return session.query(FounderSessionRecord).filter(FounderSessionRecord.revoked_at.is_(None), FounderSessionRecord.expires_at > now).update({FounderSessionRecord.revoked_at: now}, synchronize_session=False)


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
