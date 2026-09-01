import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from storage.models import Base

DEFAULT_DB_URL = os.environ.get("OPPORTUNITYOS_DB_URL", "sqlite:///opportunityos.db")


class ProductionDatabaseConfigurationError(RuntimeError):
    """Raised when production persistence configuration is missing or attempts silent SQLite fallback."""


def get_production_db_url() -> str:
    """Return the authoritative production database URL, failing closed if missing or not PostgreSQL."""
    db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not db_url:
        raise ProductionDatabaseConfigurationError(
            "Production database configuration missing: OPPORTUNITYOS_DB_URL environment variable must be set."
        )
    if not db_url.startswith("postgresql"):
        raise ProductionDatabaseConfigurationError(
            f"Production persistence strictly requires a PostgreSQL database URL (postgresql+psycopg2://...), got: '{db_url}'. Silent fallback to SQLite is prohibited in production."
        )
    return db_url


def get_engine(db_url: str | None = None, echo: bool = False, allow_sqlite: bool = False):
    """Create SQLAlchemy engine.
    
    If db_url is None:
      - Uses OPPORTUNITYOS_DB_URL if present.
      - If OPPORTUNITYOS_DB_URL is absent:
          * If allow_sqlite is True (explicit unit-test/local opt-in), returns sqlite:///opportunityos.db.
          * Otherwise, raises ProductionDatabaseConfigurationError.
    """
    if db_url is None:
        env_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        if env_url:
            db_url = env_url
        elif allow_sqlite:
            db_url = "sqlite:///opportunityos.db"
        else:
            # Fall back closed for production
            db_url = get_production_db_url()

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, echo=echo, connect_args=connect_args)


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
