"""停止の通知が「初めて届いたか」を覚えておく口。

⚠ **再送を弾くためだけにある。** 送り手は再送でも同じ ``jti`` を使うので、
弾かないと**古い通知の再送で、いま生きているセッション**を落としうる
（止められた人が入り直した直後の再送が、その新しいセッションを消す）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class LogoutDeliveryRepository(ABC):
    @abstractmethod
    def record(self, *, jti: str, now: datetime) -> bool:
        """初めての通知なら記録して ``True``。既に受けていれば ``False``。"""

    @abstractmethod
    def delete_expired(self, now: datetime) -> int:
        """効かなくなった記録を片付ける（残しても弾く相手がもう居ない）。"""


__all__ = ["LogoutDeliveryRepository"]
