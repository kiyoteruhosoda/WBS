"""取り込んだカレンダーの読み込みの状態（ADR-0037）。

取り込んだカレンダー（``CalendarKind.IMPORTED``）1 つに 1 行。最後にどこから・いつ・何件読んだかと、
URL を **購読しているとき** だけ、その URL（封じたもの）と画面に出す手掛かりを持つ。

- 購読していない（ファイル・1 回だけの URL）なら URL は持たない。読み込み直すには、もう一度
  ファイルか URL を渡す
- 購読の読み込みに失敗しても中身は前のまま残し、失敗の理由（``last_error``）だけを覚える
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class ImportSource(enum.StrEnum):
    """最後に読み込んだ入れ方。"""

    FILE = "FILE"
    URL = "URL"


@dataclass(frozen=True)
class FeedSubscription:
    """購読している URL。⚠ ``sealed_url`` は封じたもの（平文の URL はドメインに持たない）。"""

    sealed_url: str
    url_hint: str
    """画面に出す手掛かり（ホスト名と末尾だけ。秘密の部分は含めない）。"""


@dataclass
class CalendarImport:
    calendar_id: int
    source: ImportSource
    imported_at: datetime
    """最後に読み込めた時刻。"""
    event_count: int
    subscription: FeedSubscription | None = None
    last_attempt_at: datetime | None = None
    """購読の読み込みを最後に試みた時刻（成否を問わない）。"""
    last_error: str | None = None
    """最後の読み込みの失敗の理由（成功すれば消える）。"""

    @property
    def is_subscribed(self) -> bool:
        return self.subscription is not None

    def record_success(
        self, *, source: ImportSource, event_count: int, at: datetime,
        subscription: FeedSubscription | None,
    ) -> None:
        """読み込めた。購読は渡したものに置き換わる（``None`` なら購読をやめる）。"""
        self.source = source
        self.event_count = event_count
        self.imported_at = at
        self.last_attempt_at = at
        self.last_error = None
        self.subscription = subscription

    def record_failure(self, reason: str, at: datetime) -> None:
        """購読の読み込みに失敗した。中身と購読はそのまま。"""
        self.last_attempt_at = at
        self.last_error = reason

    def unsubscribe(self) -> None:
        """購読をやめる（URL を忘れる。中身は残す）。"""
        self.subscription = None
        self.last_error = None


__all__ = ["CalendarImport", "FeedSubscription", "ImportSource"]
