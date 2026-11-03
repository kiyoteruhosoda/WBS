"""実績の見える化（計画 vs 確定した実績。task #162 / ADR-0017。予定と打刻は task #543 / ADR-0070 で外した）の結果。"""

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
    """プロジェクトの枝ごと（子孫の分を積み上げる。ADR-0024）。"""


UNGROUPED_GROUP = "none"
"""タスクはあるが、カテゴリ（マイルストーン・プロジェクト）が無い・消えた。"""


@dataclass(frozen=True)
class TaskActualsRow:
    """タスク 1 行: タスクの応答（見積・実績・残）に、実績の帯と見直しの理由を足したもの。"""

    task: dict
    actual_first_date: date | None
    actual_last_date: date | None
    latest_closed_hours: float
    """Tracker から直近に届いた締めの期間でこのタスクに入った実績（時間）。"""
    review_reasons: list[RemainingReviewReason]


@dataclass(frozen=True)
class ClosedPeriod:
    """Tracker から直近に届いた締めの期間（ADR-0056）。

    ``first_day`` は Tracker の期間の初日、``last_day`` は届いた実績の最後の日、
    ``closed_at`` は届いた瞬間（naive な UTC）。
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
    """ガントの実績の帯。最初と最後の日は全期間から、日ごとの塗りは問うた範囲だけ。"""

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
    """``category:<id>`` / ``milestone:<id>`` / ``project:<id>`` / ``none`` / ``unassigned``。"""
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
    """書き出しの 1 行（期間 × 日 × タスク）。"""

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
