from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.replace("sqlite:///", "", 1)
    path = Path(db_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    database_url = settings.database_url

    _ensure_sqlite_parent(database_url)

    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)

    return create_engine(database_url, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    init_db()
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns(engine)


def _ensure_runtime_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "ingest_tasks" not in table_names:
        return

    columns = {item["name"] for item in inspector.get_columns("ingest_tasks")}
    additions = {
        "current_stage": "ALTER TABLE ingest_tasks ADD COLUMN current_stage VARCHAR(64)",
        "stage_metrics_json": "ALTER TABLE ingest_tasks ADD COLUMN stage_metrics_json TEXT",
    }

    with engine.begin() as connection:
        for column, ddl in additions.items():
            if column not in columns:
                connection.execute(text(ddl))

        if "documents" in table_names:
            document_columns = {item["name"] for item in inspector.get_columns("documents")}
            document_additions = {
                "document_number": "ALTER TABLE documents ADD COLUMN document_number VARCHAR(128)",
                "status_evidence": "ALTER TABLE documents ADD COLUMN status_evidence TEXT",
                "metadata_evidence_json": "ALTER TABLE documents ADD COLUMN metadata_evidence_json TEXT",
            }
            for column, ddl in document_additions.items():
                if column not in document_columns:
                    connection.execute(text(ddl))
