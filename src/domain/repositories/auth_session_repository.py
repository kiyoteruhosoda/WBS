from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.auth_session import AuthSession


class AuthSessionRepository(ABC):
    @abstractmethod
    def add(self, session: AuthSession) -> AuthSession: ...
    @abstractmethod
    def find_by_token(self, token: str) -> AuthSession | None: ...
    @abstractmethod
    def update(self, session: AuthSession) -> None: ...
    @abstractmethod
    def delete_by_token(self, token: str) -> None: ...
    @abstractmethod
    def delete_expired(self, now: datetime) -> int: ...
