"""「今日」の画面の要約の応答（task #160 / ADR-0015）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.application.dto.today_dto import TodaySummary
from src.presentation.api.schemas.task_schemas import TaskResponse
from src.presentation.api.schemas.time_entry_schemas import TimeEntryResponse
from src.presentation.api.schemas.types import UtcDatetime


class TaskActualResponse(BaseModel):
    """今日の実績の 1 行。未割当の打刻は ``task_id`` が null。"""

    task_id: int | None
    task_title: str | None
    seconds: int


class TodaySummaryResponse(BaseModel):
    """利用者のタイムゾーンでの今日 1 日分。

    - ``date`` は利用者の日付（``YYYY-MM-DD``）。予定の回はこの日を ``/api/calendar/occurrences`` に問う
    - ``day_start``〜``day_end`` は今日の区切り（UTC、``[開始, 終了)``）
    - ``entries`` は今日に掛かる打刻（日をまたぐ打刻はそのまま。切るのは画面）
    - ``total_seconds`` と ``actuals`` は今日の分だけ。走っている打刻は ``server_now`` まで
    - ``tasks_to_schedule`` は今日やるべきタスクのうち、まだ予定を取っていないもの（優先度の点の高い順）
    """

    date: date
    time_zone: str
    day_start: UtcDatetime
    day_end: UtcDatetime
    server_now: UtcDatetime
    running: TimeEntryResponse | None
    entries: list[TimeEntryResponse]
    total_seconds: int
    actuals: list[TaskActualResponse]
    tasks_to_schedule: list[TaskResponse]

    @classmethod
    def from_summary(cls, summary: TodaySummary) -> TodaySummaryResponse:
        return cls(
            date=summary.date,
            time_zone=summary.time_zone,
            day_start=summary.day_start,
            day_end=summary.day_end,
            server_now=summary.server_now,
            running=(
                TimeEntryResponse.from_view(summary.running)
                if summary.running is not None
                else None
            ),
            entries=[TimeEntryResponse.from_view(v) for v in summary.entries],
            total_seconds=summary.total_seconds,
            actuals=[
                TaskActualResponse(task_id=a.task_id, task_title=a.task_title, seconds=a.seconds)
                for a in summary.actuals
            ],
            tasks_to_schedule=[TaskResponse(**t) for t in summary.tasks_to_schedule],
        )


__all__ = ["TaskActualResponse", "TodaySummaryResponse"]
