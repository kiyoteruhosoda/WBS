from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text
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
    _apply_column_upgrades()
    _seed_default_user()

def _apply_column_upgrades() -> None:
    # create_all は既存テーブルの列を変更しないため、後から増減した列をここで補う
    inspector = inspect(_engine)
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "language" not in user_columns:
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'ja'"))
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "remaining_hours" in task_columns:
        # 残り時間は「見積 − 実績」で導出する方式に変更したため列ごと廃止
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks DROP COLUMN remaining_hours"))

def _seed_default_user() -> None:
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
