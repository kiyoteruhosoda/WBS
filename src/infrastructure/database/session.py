from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.schema_migration import ensure_schema_is_current

_engine = None
_SessionLocal = None


def resolve_database_url(database_url: str | None = None) -> str:
    return database_url or os.getenv("DATABASE_URL", "sqlite:///./app.db")


def init_engine(database_url: str | None = None) -> None:
    """接続を用意する。⚠ 表は作らない（形を変えるのは Alembic だけ。ADR-0006）。

    head まで上がっていない DB では起動させない（先に scripts/run_db_migrations.py）。
    """
    global _engine, _SessionLocal
    url = resolve_database_url(database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    ensure_schema_is_current(_engine)


def seed_default_user() -> None:
    with _SessionLocal() as session:
        result = session.execute(text("SELECT id FROM users WHERE id=1")).fetchone()
        if not result:
            session.execute(text(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, created_at, updated_at) "
                "VALUES (1, 'local@example.com', 'ローカルユーザー', 'Asia/Tokyo', 'ja', 1, datetime('now'), datetime('now'))"
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
