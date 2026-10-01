import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import URL


DATABASE_URL = os.getenv(
    "AUTH_DATABASE_URL",
    URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "mnm"),
        password=os.getenv("POSTGRES_PASSWORD", "mnm-local-only"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database="auth_db",
    ),
)
engine_options = {"pool_pre_ping": True}
if str(DATABASE_URL).startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()