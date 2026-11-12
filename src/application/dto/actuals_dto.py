"""Results of the actuals view (plan vs confirmed actuals; task #162 / ADR-0017. Calendar events and time punches were removed in task #543 / ADR-0070)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from src.domain.services.remaining_review import RemainingReviewReason
from src.domain.value_objects.report_period import ReportPeriod, ReportPeriodUnit


class BreakdownGroupBy(StrEnum):
    CATEGORY = "category"
    MILESTONE = "milestone"
    PROJECT = "project"
    """Per project branch (descendants rolled up, ADR-0024)."""


UNGROUPED_GROUP = "none"
"""The task exists, but its category (milestone/project) is missing or deleted."""


@dataclass(frozen=True)
class TaskActualsRow:
    """One task row: the task response (estimate, actual, remaining) plus the actuals bar and reasons to revisit."""

    task: dict
    actual_first_date: date | None
    actual_last_date: date | None
    latest_closed_hours: float
    """Actual hours logged on this task during the closed period most recently received from Tracker."""
    review_reasons: list[RemainingReviewReason]


@dataclass(frozen=True)
class ClosedPeriod:
    """The closed period most recently received from Tracker (ADR-0056).

    ``first_day`` is the first day of the Tracker period, ``last_day`` the last day of the received actuals,
    ``closed_at`` the moment it was received (naive UTC).
    """

    first_day: date
    last_day: date
    closed_at: datetime


@dataclass(frozen=True)
class TaskActualsBoard:
    latest_closed: ClosedPeriod | None
    rows: list[TaskActualsRow]


@dataclass(frozen=True)
class GanttActualDay:
    work_date: date
    seconds: int


@dataclass(frozen=True)
class GanttActualSpan:
    """Actuals bar on the Gantt chart. First and last days come from the whole period; per-day fill only within the queried range."""

    task_id: int
    first_date: date
    last_date: date
    days: list[GanttActualDay]


@dataclass(frozen=True)
class PeriodComparison:
    period: ReportPeriod
    confirmed_seconds: int


@dataclass(frozen=True)
class PeriodReport:
    unit: ReportPeriodUnit
    time_zone: str
    periods: list[PeriodComparison]


@dataclass(frozen=True)
class BreakdownGroup:
    key: str
    """``category:<id>`` / ``milestone:<id>`` / ``project:<id>`` / ``none`` / ``unassigned``."""
    name: str | None
    color: str | None


@dataclass(frozen=True)
class BreakdownPeriod:
    period: ReportPeriod
    seconds_by_group: dict[str, int]


@dataclass(frozen=True)
class Breakdown:
    unit: ReportPeriodUnit
    group_by: BreakdownGroupBy
    time_zone: str
    groups: list[BreakdownGroup]
    periods: list[BreakdownPeriod]


@dataclass(frozen=True)
class ExportRow:
    """One export row (period x day x task)."""

    period: ReportPeriod
    work_date: date
    task_id: int
    task_title: str | None
    category_name: str | None
    milestone_name: str | None
    seconds: int


__all__ = [
    "UNGROUPED_GROUP",
    "Breakdown",
    "BreakdownGroup",
    "BreakdownGroupBy",
    "BreakdownPeriod",
    "ClosedPeriod",
    "ExportRow",
    "GanttActualDay",
    "GanttActualSpan",
    "PeriodComparison",
    "PeriodReport",
    "TaskActualsBoard",
    "TaskActualsRow",
]
