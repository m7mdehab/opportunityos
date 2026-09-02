"""FastAPI app factory. Fail closed: `create_app()` with no arguments reads
required configuration from the environment and raises immediately (naming
the missing variable) rather than constructing with insecure defaults.

`uvicorn api.app:app` therefore also fails closed, because importing this
module evaluates `app = create_app()` at import time.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.logging import get_logger
from storage.engine import get_engine, get_session_factory

from .routes_api import load_truth_pack_into_state, router as api_router
from .routes_auth import router as auth_router
from .security import LoginRateLimiter, make_serializer
from .settings import Settings, load_settings

logger = get_logger("api.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the OpportunityOS FastAPI app.

    Reads settings from the environment (fail closed) when `settings` is not
    provided explicitly. Passing `settings` explicitly is intended for tests
    only -- it never reads `private/`.
    """
    resolved_settings = settings or load_settings()

    app = FastAPI(title="OpportunityOS Founder Alpha API")

    app.state.settings = resolved_settings
    app.state.session_serializer = make_serializer(resolved_settings.session_secret)
    app.state.login_rate_limiter = LoginRateLimiter()

    engine = get_engine(resolved_settings.db_url)
    app.state.engine = engine
    app.state.session_factory = get_session_factory(engine)

    app.state.loaded_truth_pack = None
    app.state.truth_pack_error = None
    app.state.truth_pack_findings = ()
    app.state.truth_pack_path_display = resolved_settings.truth_pack_path or "private/truth_pack.yaml"

    @app.middleware("http")
    async def request_id_and_logging(request: Request, call_next):
        req_id = uuid.uuid4().hex[:16]
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = req_id
        logger.info(
            "request handled",
            extra={
                "run_id": req_id,
                "component": "api.http",
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            },
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled exception",
            extra={"run_id": req_id, "component": "api.http", "extra_data": {"path": request.url.path}},
        )
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.include_router(auth_router)
    app.include_router(api_router)

    @app.on_event("startup")
    def _load_truth_pack_on_startup() -> None:
        load_truth_pack_into_state(app)

    return app


def __getattr__(name: str):
    """PEP 562 lazy module attribute.

    `import api.app` must succeed with no environment configured at all --
    otherwise `python -m unittest discover` cannot even collect the test
    suite. `uvicorn api.app:app` resolves the `app` attribute (not the bare
    import), so it still fails closed: the first access of `api.app.app`
    calls `create_app()`, which raises `MissingSettingError` naming the
    missing variable when the environment is incomplete.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
