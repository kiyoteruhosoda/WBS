from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.push_subscription import PushSubscription


class PushSubscriptionRepository(ABC):
    """⚠ 書く口は flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def list_for_user(self, user_id: int) -> list[PushSubscription]:
        """その人の購読を登録の古い順に。"""

    @abstractmethod
    def find_for_user(self, subscription_id: int, user_id: int) -> PushSubscription | None:
        """他人の購読は「無い」（``None``）。"""

    @abstractmethod
    def user_ids_with_subscriptions(self) -> list[int]:
        """購読を 1 つでも持つ利用者（送る係が回る相手）。"""

    @abstractmethod
    def save(self, subscription: PushSubscription) -> PushSubscription:
        """同じ ``endpoint`` があれば、その行を置き換える（持ち主も移る）。"""

    @abstractmethod
    def set_receives_calendar(self, subscription_id: int, receives_calendar: bool) -> None: ...

    @abstractmethod
    def mark_sent(self, subscription_id: int, at: datetime) -> None: ...

    @abstractmethod
    def delete(self, subscription_id: int) -> None: ...
