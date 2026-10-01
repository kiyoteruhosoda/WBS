"""「今日」の画面の要約（task #160 / ADR-0015）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.application.dto.time_entry_dto import TimeEntryView


@dataclass(frozen=True)
class TaskActual:
    """今日の実績の 1 行（打刻の長さをタスクごとに足したもの。未割当は ``task_id`` が None）。"""

    task_id: int | None
    task_title: str | None
    seconds: int


@dataclass(frozen=True)
class TodaySummary:
    """利用者のタイムゾーンでの「今日」1 日分。

    時刻はすべて naive な UTC。``day_start``〜``day_end`` は ``[開始, 終了)``。
    ``tasks_to_schedule`` はタスクの応答と同じ形の dict（``TaskUseCases`` が作るもの）。
    """

    date: date
    time_zone: str
    day_start: datetime
    day_end: datetime
    server_now: datetime
    running: TimeEntryView | None
    entries: list[TimeEntryView]
    total_seconds: int
    actuals: list[TaskActual]
    tasks_to_schedule: list[dict]


__all__ = ["TaskActual", "TodaySummary"]
