"""実績の見える化の応答（task #162 / ADR-0017）。時間は秒（整数）か時間（小数 2 桁）で返す。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.application.dto.actuals_dto import (
    Breakdown,
    GanttActualSpan,
    PeriodReport,
    TaskActualsBoard,
)
from src.presentation.api.schemas.task_schemas import TaskResponse
from src.presentation.api.schemas.types import UtcDatetime


class ClosedPeriodResponse(BaseModel):
    first_day: date
    last_day: date
    closed_at: UtcDatetime


class TaskActualsRowResponse(BaseModel):
    """タスク 1 行。見積・予定済み・実績・残は ``task`` の欄（タスクの一覧と同じ値）。

    ``review_reasons``: 残を見直してほしい理由（``over_estimate`` / ``no_remaining`` /
    ``unknown_remaining`` / ``stale_remaining``）。空なら見直さなくてよい。
    """

    task: TaskResponse
    actual_first_date: date | None
    actual_last_date: date | None
    latest_closed_hours: float
    review_reasons: list[str]


class TaskActualsResponse(BaseModel):
    latest_closed_period: ClosedPeriodResponse | None
    rows: list[TaskActualsRowResponse]

    @classmethod
    def from_board(cls, board: TaskActualsBoard) -> TaskActualsResponse:
        latest = board.latest_closed
        return cls(
            latest_closed_period=(
                ClosedPeriodResponse(
                    first_day=latest.first_day, last_day=latest.last_day, closed_at=latest.closed_at
                )
                if latest is not None
                else None
            ),
            rows=[
                TaskActualsRowResponse(
                    task=TaskResponse(**row.task),
                    actual_first_date=row.actual_first_date,
                    actual_last_date=row.actual_last_date,
                    latest_closed_hours=row.latest_closed_hours,
                    review_reasons=[r.value for r in row.review_reasons],
                )
                for row in board.rows
            ],
        )


class GanttActualDayResponse(BaseModel):
    date: date
    seconds: int


class GanttActualSpanResponse(BaseModel):
    task_id: int
    first_date: date
    last_date: date
    days: list[GanttActualDayResponse]

    @classmethod
    def from_span(cls, span: GanttActualSpan) -> GanttActualSpanResponse:
        return cls(
            task_id=span.task_id,
            first_date=span.first_date,
            last_date=span.last_date,
            days=[GanttActualDayResponse(date=d.work_date, seconds=d.seconds) for d in span.days],
        )


class PeriodComparisonResponse(BaseModel):
    """1 期間。``planned_*`` は予定の回（終日は除く）、``tracked_*`` は打刻、``confirmed`` は確定実績。

    ``*_off_task_*`` はタスク外（タスクに結ばない予定・未割当の打刻）。割合は 0〜1、分母 0 なら null。
    ``difference_seconds`` = 打刻 − 予定。``closed`` は締めの期間のときだけ（確定済みか）。
    """

    first_day: date
    last_day: date
    closed: bool | None
    planned_seconds: int
    planned_task_seconds: int
    planned_off_task_seconds: int
    tracked_seconds: int
    tracked_task_seconds: int
    tracked_off_task_seconds: int
    confirmed_seconds: int
    difference_seconds: int
    planned_off_task_ratio: float | None
    tracked_off_task_ratio: float | None


class PeriodReportResponse(BaseModel):
    unit: str
    time_zone: str
    periods: list[PeriodComparisonResponse]

    @classmethod
    def from_report(cls, report: PeriodReport) -> PeriodReportResponse:
        return cls(
            unit=report.unit.value,
            time_zone=report.time_zone,
            periods=[
                PeriodComparisonResponse(
                    first_day=p.period.first_day,
                    last_day=p.period.last_day,
                    closed=p.closed,
                    planned_seconds=p.planned_seconds,
                    planned_task_seconds=p.planned_task_seconds,
                    planned_off_task_seconds=p.planned_off_task_seconds,
                    tracked_seconds=p.tracked_seconds,
                    tracked_task_seconds=p.tracked_task_seconds,
                    tracked_off_task_seconds=p.tracked_off_task_seconds,
                    confirmed_seconds=p.confirmed_seconds,
                    difference_seconds=p.difference_seconds,
                    planned_off_task_ratio=p.planned_off_task_ratio,
                    tracked_off_task_ratio=p.tracked_off_task_ratio,
                )
                for p in report.periods
            ],
        )


class BreakdownGroupResponse(BaseModel):
    """``key`` は ``category:<id>`` / ``milestone:<id>`` / ``project:<id>`` / ``none``（未分類）/
    ``unassigned``（タスク外）。プロジェクトは枝ごとの合計（子孫の分を含む）。"""

    key: str
    name: str | None
    color: str | None


class BreakdownPeriodResponse(BaseModel):
    first_day: date
    last_day: date
    seconds_by_group: dict[str, int]


class BreakdownResponse(BaseModel):
    unit: str
    group_by: str
    source: str
    time_zone: str
    groups: list[BreakdownGroupResponse]
    periods: list[BreakdownPeriodResponse]

    @classmethod
    def from_breakdown(cls, breakdown: Breakdown) -> BreakdownResponse:
        return cls(
            unit=breakdown.unit.value,
            group_by=breakdown.group_by.value,
            source=breakdown.source.value,
            time_zone=breakdown.time_zone,
            groups=[
                BreakdownGroupResponse(key=g.key, name=g.name, color=g.color)
                for g in breakdown.groups
            ],
            periods=[
                BreakdownPeriodResponse(
                    first_day=p.period.first_day,
                    last_day=p.period.last_day,
                    seconds_by_group=p.seconds_by_group,
                )
                for p in breakdown.periods
            ],
        )


__all__ = [
    "BreakdownResponse",
    "GanttActualSpanResponse",
    "PeriodReportResponse",
    "TaskActualsResponse",
]
