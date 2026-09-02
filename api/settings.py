"""Fail-closed settings for the OpportunityOS FastAPI service.

Every secret and every piece of persistence configuration is read from the
environment and validated eagerly. There is no default password, no default
session secret, and no silent fallback database. A missing variable raises
``MissingSettingError`` naming the exact variable, so ``create_app()`` (and
therefore ``uvicorn api.app:app``) refuses to start rather than serving with
insecure defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from storage.engine import get_production_db_url, ProductionDatabaseConfigurationError

#: Session cookie name, fixed by the API contract.
SESSION_COOKIE_NAME = "oos_session"

#: How long a signed session cookie remains valid, in seconds.
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60

#: Default high-fit threshold on the 0-100 fit_score scale.
DEFAULT_HIGH_FIT_THRESHOLD = 70.0

#: Login attempts allowed per rate-limit window.
LOGIN_RATE_LIMIT_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60


class MissingSettingError(RuntimeError):
    """Raised when a required environment variable is absent. Names the variable."""


@dataclass(frozen=True, slots=True)
class Settings:
    db_url: str
    founder_password: str
    session_secret: str
    high_fit_threshold: float = DEFAULT_HIGH_FIT_THRESHOLD
    truth_pack_path: str | None = None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingSettingError(
            f"Required environment variable '{name}' is missing or empty; "
            "OpportunityOS API refuses to start without it."
        )
    return value


def load_settings() -> Settings:
    """Build ``Settings`` from the environment, failing closed on any gap.

    ``OPPORTUNITYOS_DB_URL`` is additionally validated through
    ``storage.engine.get_production_db_url`` so a non-PostgreSQL URL is
    also refused, matching the fail-closed persistence invariant used
    everywhere else in the codebase.
    """
    try:
        db_url = get_production_db_url(os.environ.get("OPPORTUNITYOS_DB_URL"))
    except ProductionDatabaseConfigurationError as error:
        raise MissingSettingError(
            f"Required environment variable 'OPPORTUNITYOS_DB_URL' is invalid: {error}"
        ) from error

    founder_password = _require_env("OPPORTUNITYOS_FOUNDER_PASSWORD")
    session_secret = _require_env("OPPORTUNITYOS_SESSION_SECRET")

    threshold_raw = os.environ.get("OPPORTUNITYOS_HIGH_FIT_THRESHOLD")
    if threshold_raw:
        try:
            high_fit_threshold = float(threshold_raw)
        except ValueError as error:
            raise MissingSettingError(
                "Environment variable 'OPPORTUNITYOS_HIGH_FIT_THRESHOLD' must be a number, "
                f"got: {threshold_raw!r}"
            ) from error
    else:
        high_fit_threshold = DEFAULT_HIGH_FIT_THRESHOLD

    truth_pack_path = os.environ.get("OPPORTUNITYOS_TRUTH_PACK_PATH") or None

    return Settings(
        db_url=db_url,
        founder_password=founder_password,
        session_secret=session_secret,
        high_fit_threshold=high_fit_threshold,
        truth_pack_path=truth_pack_path,
    )
