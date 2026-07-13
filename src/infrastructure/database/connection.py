from __future__ import annotations
from src.infrastructure.database.session import init_engine

def init_db(database_url: str | None = None) -> None:
    init_engine(database_url)
