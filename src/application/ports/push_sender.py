"""端末へ通知を送る口（Web Push。実装は ``src/infrastructure/push/web_push_sender.py``。ADR-0031）。"""

from __future__ import annotations

import enum
from typing import Protocol

from src.domain.entities.push_subscription import PushSubscription
from src.domain.value_objects.push_notice import PushNotice


class PushOutcome(enum.StrEnum):
    DELIVERED = "delivered"
    #: 通知サービスが「その購読はもう無い」と答えた（404 / 410）。購読を外す。
    GONE = "gone"
    #: それ以外の失敗。購読は残す（通知サービスの一時的な不調かもしれない）。
    FAILED = "failed"


class PushSender(Protocol):
    @property
    def enabled(self) -> bool:
        """送れる設定になっているか（鍵が無い・読めないなら偽。⚠ 既定は偽）。"""
        ...

    def public_key(self) -> str | None:
        """ブラウザの購読に渡す公開鍵（base64url の非圧縮の点）。送れないなら ``None``。"""
        ...

    def send(self, subscription: PushSubscription, notice: PushNotice) -> PushOutcome: ...


class DisabledPushSender:
    """送らない（鍵の無い配備・試験の既定）。"""

    @property
    def enabled(self) -> bool:
        return False

    def public_key(self) -> str | None:
        return None

    def send(self, subscription: PushSubscription, notice: PushNotice) -> PushOutcome:
        return PushOutcome.FAILED


__all__ = ["DisabledPushSender", "PushOutcome", "PushSender"]
