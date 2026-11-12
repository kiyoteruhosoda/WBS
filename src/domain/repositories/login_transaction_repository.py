from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.login_transaction import LoginTransaction


class LoginTransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: LoginTransaction) -> LoginTransaction: ...
    @abstractmethod
    def consume(self, state: str) -> LoginTransaction | None:
        """Take the round trip matching ``state`` and delete it at the same time (one use only)."""
    @abstractmethod
    def find(self, state: str) -> LoginTransaction | None:
        """Read the round trip matching ``state`` (without deleting). Used only to decide which cleanup the return goes to."""
    @abstractmethod
    def delete_expired(self, now: datetime) -> int: ...
