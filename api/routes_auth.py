"""Login, logout, and session-status routes. Not gated by `require_session`
-- these routes ARE the session boundary."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from core.logging import get_logger

from .security import (
    constant_time_password_check,
    is_localhost_bind,
    sign_session,
    verify_session,
)
from .settings import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS

logger = get_logger("api.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    # Server-side signal only (ASGI scope["server"], the transport-reported
    # bind address) -- never a client-supplied header. See
    # api.security.is_localhost_bind for why.
    # A same-container reverse proxy reaches FastAPI over loopback even when
    # the founder-facing connection is public HTTPS. Production explicitly
    # forces Secure so that topology cannot weaken the browser cookie.
    secure = request.app.state.settings.force_secure_cookies or not is_localhost_bind(
        request.scope.get("server")
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    settings = request.app.state.settings
    limiter = request.app.state.login_rate_limiter

    # Finding 2 (council, auth review): a limiter keyed by client address is
    # trivially bypassable on loopback (the client picks its own source
    # address there). This is a single-founder service with no legitimate
    # second client to distinguish, so the budget is one global bucket --
    # see api.security.LoginRateLimiter.
    retry_after = limiter.check_and_record()
    if retry_after is not None:
        logger.info(
            "login rate limited",
            extra={"component": "api.auth", "extra_data": {"retry_after_seconds": retry_after}},
        )
        response.status_code = 429
        return {"detail": "too many attempts", "retry_after_seconds": retry_after}

    if not constant_time_password_check(payload.password, settings.founder_password):
        logger.info("login failed", extra={"component": "api.auth", "extra_data": {"outcome": "invalid_credentials"}})
        response.status_code = 401
        return {"detail": "invalid credentials"}

    token = sign_session(request.app.state.session_serializer)
    _set_session_cookie(response, request, token)
    logger.info("login succeeded", extra={"component": "api.auth", "extra_data": {"outcome": "ok"}})
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/me")
def me(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if verify_session(request.app.state.session_serializer, token):
        return {"authenticated": True}
    response.status_code = 401
    return {"detail": "not authenticated"}
