"""Shared FastAPI dependencies: DB session, session-auth enforcement, and
per-request structured logging context."""

from __future__ import annotations

import uuid
from typing import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from storage.repository import StorageRepository

from .security import get_durable_session, verify_session
from .settings import SESSION_COOKIE_NAME


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        session.close()



def get_repository(session: Session = Depends(get_db)) -> StorageRepository:
    return StorageRepository(session)


def require_session(request: Request) -> None:
    """Enforce a valid founder session. Raises 401 otherwise.

    This is the single fail-closed gate: it is attached once, at the
    router level, to every non-auth route rather than repeated per
    endpoint, so a route added later cannot accidentally ship unguarded.
    """
    settings = request.app.state.settings
    cookie_name = "__Host-oos_session" if settings.cloud_mode else SESSION_COOKIE_NAME
    token = request.cookies.get(cookie_name)
    if settings.cloud_mode:
        session = request.app.state.session_factory()
        try:
            valid = get_durable_session(session, token, settings.session_secret) is not None
            session.commit()
        finally:
            session.close()
    else:
        valid = verify_session(request.app.state.session_serializer, token)
    if not valid:
        raise HTTPException(status_code=401, detail="not authenticated")


def request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    generated = uuid.uuid4().hex[:16]
    request.state.request_id = generated
    return generated
