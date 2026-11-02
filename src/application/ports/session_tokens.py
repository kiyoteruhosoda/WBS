"""このアプリが自分で出すトークン（ADR-0069）。assay のトークンとは別物で、中身を知るのはこのアプリだけ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.dto.auth_dto import AuthenticatedUserDTO


@dataclass(frozen=True)
class AccessTokenContents:
    user: AuthenticatedUserDTO
    session_id: str


@dataclass(frozen=True)
class RefreshTokenContents:
    user_id: int
    session_id: str
    jti: str


class SessionTokens(ABC):
    @property
    @abstractmethod
    def refresh_lifetime(self) -> timedelta: ...

    @abstractmethod
    def access_token(self, user: AuthenticatedUserDTO, *, session_id: str, now: datetime) -> str:
        """⚠ **検証が DB を引かないので、利用者について要るものは全部載せる。**"""

    @abstractmethod
    def refresh_token(self, user_id: int, *, session_id: str, jti: str, now: datetime) -> str: ...

    @abstractmethod
    def logout_token(self, user_id: int, *, session_id: str, now: datetime) -> str:
        """ログインを終わらせることしかできない札。"""

    @abstractmethod
    def read_access(self, token: str, *, now: datetime) -> AccessTokenContents | None:
        """署名と期限を確かめて読む。読めなければ ``None``。"""

    @abstractmethod
    def read_refresh(self, token: str, *, now: datetime) -> RefreshTokenContents | None: ...

    @abstractmethod
    def read_logout(self, token: str, *, now: datetime) -> str | None:
        """札が指す控えの番号。"""
