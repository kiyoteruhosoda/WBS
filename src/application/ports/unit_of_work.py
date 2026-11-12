"""Boundary of a use case (committing the transaction).

SQLAlchemy's ``Session`` satisfies this shape as is. Operations that write two events in one use case
(splitting off this occurrence, splitting the following ones) commit only once at the end.
"""

from __future__ import annotations

from typing import Protocol


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
