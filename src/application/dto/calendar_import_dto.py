"""カレンダーの取り込み（ADR-0037）の入出力。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from src.domain.value_objects.event_color import EventColorKey


@dataclass(frozen=True)
class FileFeedSource:
    """上げたファイルの中身。"""

    content: bytes


@dataclass(frozen=True)
class UrlFeedSource:
    """URL から読む。``subscribe`` なら URL を（封じて）覚え、定期的に読み込み直す。"""

    url: str
    subscribe: bool = False


FeedSource = FileFeedSource | UrlFeedSource


@dataclass(frozen=True)
class ImportedOccurrenceView:
    """画面へ渡す取り込んだ回（閲覧者のタイムゾーンへ直したもの）。

    終日の回は日ごとに 1 つ（2 日にまたがる終日の回は 2 つ）。時刻のある回は開始の日に 1 つ。
    """

    calendar_id: int
    title: str
    location: str | None
    start_utc: datetime
    duration_minutes: int
    date: date
    start_time: time
    is_all_day: bool
    calendar_color_key: EventColorKey


__all__ = ["FeedSource", "FileFeedSource", "ImportedOccurrenceView", "UrlFeedSource"]
