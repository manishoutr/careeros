"""Database setup.

SQLAlchemy works against SQLite (default, zero setup) or PostgreSQL
(set DATABASE_URL). JSON blobs are stored as Text so the same code runs
on both engines without dialect-specific types.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def init_db() -> None:
    from . import models  # noqa: F401  (register models)
    Base.metadata.create_all(engine)
    _migrate_jobs_table()
    from .services import vectorstore
    vectorstore.init()


# Columns added after the first demo shipped. create_all covers fresh
# databases; existing ones get plain ALTER TABLE additions (SQLite and
# Postgres both accept ADD COLUMN with a default).
_JOB_COLUMN_MIGRATIONS = {
    "source": "VARCHAR DEFAULT 'seed'",
    "source_id": "VARCHAR DEFAULT ''",
    "last_verified_at": "VARCHAR DEFAULT ''",
    "is_expired": "INTEGER DEFAULT 0",
    "embedding_model": "VARCHAR DEFAULT ''",
}


def _migrate_jobs_table() -> None:
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if not insp.has_table("jobs"):
        return
    existing = {c["name"] for c in insp.get_columns("jobs")}
    missing = {k: v for k, v in _JOB_COLUMN_MIGRATIONS.items() if k not in existing}
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
