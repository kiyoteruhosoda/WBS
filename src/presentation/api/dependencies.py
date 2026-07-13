import sqlite3
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request

from src.infrastructure.database.connection import get_connection


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]
