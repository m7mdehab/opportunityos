import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from storage.models import Base

DEFAULT_DB_URL = os.environ.get("OPPORTUNITYOS_DB_URL", "sqlite:///opportunityos.db")

def get_engine(db_url: str = DEFAULT_DB_URL, echo: bool = False):
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, echo=echo, connect_args=connect_args)

def init_db(engine):
    Base.metadata.create_all(engine)

def get_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
