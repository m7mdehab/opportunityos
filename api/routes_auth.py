"""Login, logout, and session-status routes. Not gated by `require_session`
-- these routes ARE the session boundary."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from core.logging import get_logger

from .security import (
    constant_time_password_check,
    verify_founder_password,
    _audit,
    create_durable_session,
    durable_rate_limit,
    get_durable_session,
    revoke_all_durable_sessions,
    revoke_durable_session,
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
    settings = request.app.state.settings
    cookie_name = "__Host-oos_session" if settings.cloud_mode else SESSION_COOKIE_NAME
    response.set_cookie(
        key=cookie_name,
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
    # Password verification and session persistence are separate decisions.
    # A hash in local mode is still a local signed-session deployment.
    durable = bool(settings.cloud_mode)
    db = request.app.state.session_factory() if durable else None
    limiter = request.app.state.login_rate_limiter

    # Finding 2 (council, auth review): a limiter keyed by client address is
    # trivially bypassable on loopback (the client picks its own source
    # address there). This is a single-founder service with no legitimate
    # second client to distinguish, so the budget is one global bucket --
    # see api.security.LoginRateLimiter.
    retry_after = durable_rate_limit(db) if durable else limiter.check_and_record()
    if retry_after is not None:
        logger.info(
            "login rate limited",
            extra={"component": "api.auth", "extra_data": {"retry_after_seconds": retry_after}},
        )
        response.status_code = 429
        if db is not None:
            _audit(db, "LOGIN_RATE_LIMITED", "blocked", getattr(request.state, "request_id", None))
            db.commit(); db.close()
        return {"detail": "too many attempts", "retry_after_seconds": retry_after}

    if settings.founder_password_hash:
        valid_password = verify_founder_password(payload.password, settings.founder_password_hash)
    else:
        valid_password = constant_time_password_check(payload.password, settings.founder_password or "")
    if not valid_password:
        logger.info("login failed", extra={"component": "api.auth", "extra_data": {"outcome": "invalid_credentials"}})
        response.status_code = 401
        if db is not None:
            _audit(db, "LOGIN_FAILURE", "invalid_credentials", getattr(request.state, "request_id", None))
            db.commit(); db.close()
        return {"detail": "invalid credentials"}

    if durable:
        token, row = create_durable_session(db, settings.session_secret, user_agent=request.headers.get("user-agent"))
        _audit(db, "LOGIN_SUCCESS", "ok", getattr(request.state, "request_id", None), row.id)
        db.commit(); db.close()
    else:
        token = sign_session(request.app.state.session_serializer)
    _set_session_cookie(response, request, token)
    logger.info("login succeeded", extra={"component": "api.auth", "extra_data": {"outcome": "ok"}})
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    settings = request.app.state.settings
    cookie_name = "__Host-oos_session" if settings.cloud_mode else SESSION_COOKIE_NAME
    if settings.cloud_mode:
        db = request.app.state.session_factory()
        session_id = revoke_durable_session(db, request.cookies.get(cookie_name), settings.session_secret)
        _audit(db, "LOGOUT", "ok", getattr(request.state, "request_id", None), session_id)
        db.commit(); db.close()
    response.delete_cookie(cookie_name, path="/", secure=bool(settings.cloud_mode), httponly=bool(settings.cloud_mode), samesite="lax")
    return {"authenticated": False}


@router.post("/logout-all")
def logout_all(request: Request, response: Response):
    settings = request.app.state.settings
    if settings.cloud_mode:
        db = request.app.state.session_factory()
        token = request.cookies.get("__Host-oos_session")
        current = get_durable_session(db, token, settings.session_secret)
        if current is None:
            db.close()
            response.status_code = 401
            return {"detail": "not authenticated"}
        count = revoke_all_durable_sessions(db)
        _audit(db, "LOGOUT_ALL", "ok", getattr(request.state, "request_id", None))
        db.commit(); db.close()
        response.delete_cookie("__Host-oos_session", path="/", secure=True, httponly=True, samesite="lax")
        return {"authenticated": False, "revoked_sessions": count}
    if not verify_session(request.app.state.session_serializer, request.cookies.get(SESSION_COOKIE_NAME)):
        response.status_code = 401
        return {"detail": "not authenticated"}
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"authenticated": False, "revoked_sessions": 0}


@router.get("/me")
def me(request: Request, response: Response):
    settings = request.app.state.settings
    cookie_name = "__Host-oos_session" if settings.cloud_mode else SESSION_COOKIE_NAME
    token = request.cookies.get(cookie_name)
    if settings.cloud_mode:
        db = request.app.state.session_factory()
        row = get_durable_session(db, token, settings.session_secret)
        if row is not None:
            db.commit(); db.close()
            return {"authenticated": True}
        db.close()
    elif verify_session(request.app.state.session_serializer, token):
        return {"authenticated": True}
    response.status_code = 401
    return {"detail": "not authenticated"}
