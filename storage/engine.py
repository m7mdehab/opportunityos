import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from storage.models import Base

class ProductionDatabaseConfigurationError(RuntimeError):
    """Raised when production persistence configuration is missing or attempts silent SQLite fallback."""


def get_production_db_url(db_url: str | None = None) -> str:
    """Return the authoritative production database URL, failing closed if missing or not PostgreSQL."""
    resolved_url = db_url if db_url is not None else os.environ.get("OPPORTUNITYOS_DB_URL")
    if not resolved_url:
        raise ProductionDatabaseConfigurationError(
            "Production database configuration missing: OPPORTUNITYOS_DB_URL environment variable must be set."
        )
    if not resolved_url.startswith("postgresql"):
        raise ProductionDatabaseConfigurationError(
            f"Production persistence strictly requires a PostgreSQL database URL (postgresql+psycopg2://...), got: '{resolved_url}'. Silent fallback to SQLite is prohibited in production."
        )
    return resolved_url


def get_engine(
    db_url: str | None = None,
    echo: bool = False,
    allow_sqlite: bool = False,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
    pool_pre_ping: bool = False,
    application_name: str | None = None,
):
    """Create a SQLAlchemy engine.

    Pool controls are optional so existing application callers keep SQLAlchemy's
    historical defaults. Hosted worker processes can explicitly provide a small,
    finite PostgreSQL pool to avoid retaining more Supavisor session-mode
    connections than the worker can actually use concurrently. An optional
    PostgreSQL application_name makes live pool attribution observable without
    exposing credentials or payload data.

    If db_url is None:
      - Uses OPPORTUNITYOS_DB_URL if present.
      - If OPPORTUNITYOS_DB_URL is absent:
          * If allow_sqlite is True (explicit unit-test/local opt-in), returns sqlite:///opportunityos.db.
          * Otherwise, raises ProductionDatabaseConfigurationError.
    """
    if db_url is None:
        env_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if env_url:
            if not env_url.startswith("postgresql") and not allow_sqlite:
                raise ProductionDatabaseConfigurationError(
                    f"Production persistence strictly requires a PostgreSQL database URL (postgresql+psycopg2://...), got: '{env_url}'."
                )
            db_url = env_url
        elif allow_sqlite:
            db_url = "sqlite:///opportunityos.db"
        else:
            # Fall back closed for production
            db_url = get_production_db_url()

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif application_name:
        connect_args["application_name"] = application_name

    engine_kwargs = {
        "echo": echo,
        "connect_args": connect_args,
        "pool_pre_ping": pool_pre_ping,
    }

    if not db_url.startswith("sqlite"):
        if pool_size is not None:
            if pool_size < 1:
                raise ValueError("pool_size must be >= 1")
            engine_kwargs["pool_size"] = pool_size
        if max_overflow is not None:
            if max_overflow < 0:
                raise ValueError("max_overflow must be >= 0")
            engine_kwargs["max_overflow"] = max_overflow
        if pool_timeout is not None:
            if pool_timeout <= 0:
                raise ValueError("pool_timeout must be > 0")
            engine_kwargs["pool_timeout"] = pool_timeout

    engine = create_engine(db_url, **engine_kwargs)

    if application_name and not db_url.startswith("sqlite"):
        # Supavisor can replace startup-packet application_name with its own
        # backend label. Set the PostgreSQL GUC after checkout so live
        # pg_stat_activity attribution remains observable through the pooler.
        @event.listens_for(engine, "connect")
        def _set_application_name(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(
                    "SELECT set_config('application_name', %s, false)",
                    (application_name,),
                )
            finally:
                cursor.close()

    return engine


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session_factory(engine, *, expire_on_commit: bool = True):
    """Return a session factory with explicit expiration semantics.

    Application callers retain SQLAlchemy's historical expiration behavior. The
    long-running worker runtime passes ``expire_on_commit=False`` so the
    committed claim can be read without an implicit refresh transaction before
    network-bound handler work begins.
    """
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=expire_on_commit)
