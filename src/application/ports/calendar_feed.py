"""外の iCalendar（.ics）を読み込む口（ADR-0037）。実装は ``src/infrastructure/calendar_feed/``。

- ``CalendarFeedFetcher``: URL から中身を取る（https だけ・内側の宛先は断る・大きさの上限）
- ``CalendarFeedParser``: 中身を回の一覧にする（繰り返しは期間の中で展開する）
- ``FeedUrlCipher``: 購読する URL を封じる・開く（鍵の無い配備では購読できない）

失敗は ``CalendarFeedError``（理由の符号 ``reason`` を持つ。画面が言葉に直す）。
"""

from __future__ import annotations

import enum
from datetime import date
from typing import Protocol

from src.domain.value_objects.imported_occurrence import ImportedOccurrence


class FeedFailure(enum.StrEnum):
    """読み込めなかった理由（API の ``detail`` と ``last_error`` にそのまま出す）。"""

    INVALID_URL = "invalid_url"
    """https（webcal）の URL ではない。"""
    BLOCKED_ADDRESS = "blocked_address"
    """宛先が内側（私設・ループバックなど）のアドレス。"""
    UNREACHABLE = "unreachable"
    """つながらない・時間切れ。"""
    NOT_FOUND = "not_found"
    """404 / 410（公開を止めた・URL が変わった）。"""
    FORBIDDEN = "forbidden"
    """401 / 403。"""
    HTTP_ERROR = "http_error"
    """そのほかの HTTP の失敗。"""
    TOO_LARGE = "too_large"
    """大きすぎる。"""
    NOT_ICALENDAR = "not_icalendar"
    """iCalendar として読めない。"""
    TOO_MANY_EVENTS = "too_many_events"
    """期間の中の回が多すぎる。"""
    SUBSCRIPTION_UNAVAILABLE = "subscription_unavailable"
    """この配備には URL を封じる鍵が無く、購読できない。"""


class CalendarFeedError(Exception):
    def __init__(self, reason: FeedFailure) -> None:
        self.reason = reason
        super().__init__(reason.value)


class CalendarFeedFetcher(Protocol):
    def fetch(self, url: str) -> bytes:
        """URL の中身。読めなければ ``CalendarFeedError``。"""
        ...


class CalendarFeedParser(Protocol):
    def parse(
        self, content: bytes, *, from_date: date, to_date: date, default_time_zone: str
    ) -> list[ImportedOccurrence]:
        """``[from_date, to_date]`` に掛かる回。時刻のゾーンが書かれていない回は
        ``default_time_zone`` の壁時計とみなす。読めなければ ``CalendarFeedError``。"""
        ...


class FeedUrlCipher(Protocol):
    @property
    def available(self) -> bool:
        """封じる鍵があるか（無ければ購読できない）。"""
        ...

    def seal(self, url: str) -> str: ...

    def open(self, sealed: str) -> str:
        """封じたものを開く。開けなければ（鍵を替えたなど）``CalendarFeedError``。"""
        ...


class NoFeedUrlCipher:
    """鍵の無い配備（購読はできない。1 回だけの読み込みとファイルはできる）。"""

    @property
    def available(self) -> bool:
        return False

    def seal(self, url: str) -> str:
        raise CalendarFeedError(FeedFailure.SUBSCRIPTION_UNAVAILABLE)

    def open(self, sealed: str) -> str:
        raise CalendarFeedError(FeedFailure.SUBSCRIPTION_UNAVAILABLE)


__all__ = [
    "CalendarFeedError",
    "CalendarFeedFetcher",
    "CalendarFeedParser",
    "FeedFailure",
    "FeedUrlCipher",
    "NoFeedUrlCipher",
]
