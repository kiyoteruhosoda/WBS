from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.value_objects.push_kind import PushKind


class PushDispatchRepository(ABC):
    """送った通知の記録（同じ通知を 2 度送らない。ADR-0031 の 5）。"""

    @abstractmethod
    def claim(self, user_id: int, kind: PushKind, key: str, at: datetime) -> bool:
        """``(user_id, kind, key)`` を送る権利を取る。**確定まで行う。**

        取れたら ``True``。すでに記録がある（ほかのプロセスが先に取った・前の周回で送った）なら
        ``False``。⚠ web は複数のワーカーで動き、送る係も同じ時刻にプロセスの数だけ走るので、
        取り合いは表の一意制約で決める。
        """

    @abstractmethod
    def purge_before(self, at: datetime) -> None:
        """``at`` より前の記録を消す（もう同じ通知が来ない古いもの）。確定まで行う。"""
