from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.refresh_session import RefreshSession
from src.domain.value_objects.federated_identity import FederatedIdentity


class RefreshSessionRepository(ABC):
    @abstractmethod
    def add(self, session: RefreshSession) -> None: ...
    @abstractmethod
    def find(self, session_id: str) -> RefreshSession | None: ...
    @abstractmethod
    def delete(self, session_id: str) -> None: ...
    @abstractmethod
    def delete_expired(self, now: datetime) -> int: ...

    @abstractmethod
    def extend(self, session_id: str, *, idp_session_id: str | None, expires_at: datetime) -> bool:
        """続けたログインの期限を延ばし、IdP 側のログインを付け替える（ADR-0071）。行が無ければ偽。"""

    @abstractmethod
    def delete_for_identity(
        self, identity: FederatedIdentity, *, idp_session_id: str | None = None
    ) -> int:
        """IdP 上の本人で引いて、このアプリのログインを終わらせる（消した数を返す）。

        ``idp_session_id`` を渡すと、**その IdP のログインから始まったものだけ**を
        終わらせる。渡さなければその人のログインをすべて終わらせる。

        ⚠ **本人が本人であることは、ここでは確かめない。** 呼ぶ側（停止の通知・定期照合）が
        IdP の署名で確かめてから呼ぶ。
        """

    @abstractmethod
    def delete_for_idp_session(self, *, issuer: str, idp_session_id: str) -> int:
        """``sub`` の無い通知のため、``sid`` だけで引いて終わらせる。

        仕様は ``sub`` か ``sid`` のどちらかがあればよいとしている（§2.6）ので、
        ``sid`` しか無い通知も宛名として成立する。
        """
