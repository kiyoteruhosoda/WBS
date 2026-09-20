from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.auth_session import AuthSession
from src.domain.value_objects.federated_identity import FederatedIdentity


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

    @abstractmethod
    def delete_for_identity(
        self, identity: FederatedIdentity, *, idp_session_id: str | None = None
    ) -> int:
        """IdP 上の本人で引いて、このアプリのセッションを終わらせる（消した数を返す）。

        ``idp_session_id`` を渡すと、**その IdP のログインから始まったセッションだけ**を
        終わらせる。渡さなければその人のセッションをすべて終わらせる。

        ⚠ **本人が本人であることは、ここでは確かめない。** 呼ぶ側（停止の通知・定期照合）が
        IdP の署名で確かめてから呼ぶ。
        """

    @abstractmethod
    def delete_for_idp_session(self, *, issuer: str, idp_session_id: str) -> int:
        """``sub`` の無い通知のため、``sid`` だけで引いて終わらせる。

        仕様は ``sub`` か ``sid`` のどちらかがあればよいとしている（§2.6）ので、
        ``sid`` しか無い通知も宛名として成立する。
        """
