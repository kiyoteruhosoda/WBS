"""Responses for the actuals visualization (task #162 / ADR-0017). Durations are returned in seconds (int) or hours (2 decimals)."""

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
    """The most recent closing period received from Tracker (first day, last day of the received actuals, time received)."""

    first_day: date
    last_day: date
    closed_at: UtcDatetime


class TaskActualsRowResponse(BaseModel):
    """One task row. Estimate, actual and remaining are the ``task`` fields (same values as the task list).

    ``review_reasons``: why the remaining time should be reviewed (``over_estimate`` / ``no_remaining`` /
    ``unknown_remaining`` / ``stale_remaining``). Empty means no review is needed.
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
    """Confirmed actuals for one period (seconds)."""

    first_day: date
    last_day: date
    confirmed_seconds: int


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
                    confirmed_seconds=p.confirmed_seconds,
                )
                for p in report.periods
            ],
        )


class BreakdownGroupResponse(BaseModel):
    """``key`` is ``category:<id>`` / ``milestone:<id>`` / ``project:<id>`` / ``none`` (uncategorized).
    Projects are per-branch totals (including descendants)."""

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
    time_zone: str
    groups: list[BreakdownGroupResponse]
    periods: list[BreakdownPeriodResponse]

    @classmethod
    def from_breakdown(cls, breakdown: Breakdown) -> BreakdownResponse:
        return cls(
            unit=breakdown.unit.value,
            group_by=breakdown.group_by.value,
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
