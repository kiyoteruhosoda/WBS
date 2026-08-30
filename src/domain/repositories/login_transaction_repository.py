from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.login_transaction import LoginTransaction


class LoginTransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: LoginTransaction) -> LoginTransaction: ...
    @abstractmethod
    def consume(self, state: str) -> LoginTransaction | None:
        """``state`` に対応する往復を取り出し、同時に消す（1 回きり）。"""
    @abstractmethod
    def delete_expired(self, now: datetime) -> int: ...
