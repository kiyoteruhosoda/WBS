from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.models import Base

_engine = None
_SessionLocal = None

def init_engine(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./app.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(_engine)
    _seed_default_user()

def _seed_default_user() -> None:
    with _SessionLocal() as session:
        result = session.execute(text("SELECT id FROM users WHERE id=1")).fetchone()
        if not result:
            session.execute(text(
                "INSERT INTO users (id, email, display_name, timezone, is_active, created_at, updated_at) "
                "VALUES (1, 'local@example.com', 'ローカルユーザー', 'Asia/Tokyo', 1, datetime('now'), datetime('now'))"
            ))
            session.commit()

def get_engine():
    return _engine

def get_session_factory():
    return _SessionLocal

def get_db_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Engine not initialized. Call init_engine() first.")
    return _SessionLocal()
