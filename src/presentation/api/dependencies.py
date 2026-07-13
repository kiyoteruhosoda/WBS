from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.infrastructure.database.session import get_db_session


def get_db() -> Generator[Session, None, None]:
    session = get_db_session()
    try:
        yield session
    finally:
        session.close()

DbDep = Annotated[Session, Depends(get_db)]
