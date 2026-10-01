"""実績の見える化（予定 vs 実績・計画 vs 実績。task #162 / ADR-0017）の結果。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from src.domain.entities.closing_period import ClosingPeriod
from src.domain.services.remaining_review import RemainingReviewReason
from src.domain.value_objects.report_period import ReportPeriod, ReportPeriodUnit


class TimeSource(StrEnum):
    """どの時間を数えるか。"""

    PLANNED = "planned"
    """予定の回（終日は除く）。タスクに結んでいない予定はタスク外。"""
    TRACKED = "tracked"
    """打刻（下書き。走っている打刻は今まで）。未割当はタスク外。"""
    CONFIRMED = "confirmed"
    """確定した実績（``work_logs``。締めで作ったもの・手で書いたもの）。"""


class BreakdownGroupBy(StrEnum):
    CATEGORY = "category"
    MILESTONE = "milestone"


UNASSIGNED_GROUP = "unassigned"
"""タスク外（未割当の打刻・タスクに結ばない予定）。"""
UNGROUPED_GROUP = "none"
"""タスクはあるが、カテゴリ（マイルストーン）が無い・消えた。"""


@dataclass(frozen=True)
class TaskActualsRow:
    """タスク 1 行: タスクの応答（見積・予定済み・実績・残）に、実績の帯と見直しの理由を足したもの。"""

    task: dict
    actual_first_date: date | None
    actual_last_date: date | None
    latest_closed_hours: float
    """直近に確定した締めの期間でこのタスクに入った実績（時間）。"""
    review_reasons: list[RemainingReviewReason]


@dataclass(frozen=True)
class TaskActualsBoard:
    latest_closed: ClosingPeriod | None
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
    closed: bool | None
    """締めの期間なら確定済みか。週・月は None。"""
    planned_task_seconds: int
    planned_off_task_seconds: int
    tracked_task_seconds: int
    tracked_off_task_seconds: int
    confirmed_seconds: int

    @property
    def planned_seconds(self) -> int:
        return self.planned_task_seconds + self.planned_off_task_seconds

    @property
    def tracked_seconds(self) -> int:
        return self.tracked_task_seconds + self.tracked_off_task_seconds

    @property
    def difference_seconds(self) -> int:
        """打刻 − 予定（正なら予定より多く働いた）。"""
        return self.tracked_seconds - self.planned_seconds

    @property
    def planned_off_task_ratio(self) -> float | None:
        return _ratio(self.planned_off_task_seconds, self.planned_seconds)

    @property
    def tracked_off_task_ratio(self) -> float | None:
        return _ratio(self.tracked_off_task_seconds, self.tracked_seconds)


@dataclass(frozen=True)
class PeriodReport:
    unit: ReportPeriodUnit
    time_zone: str
    periods: list[PeriodComparison]


@dataclass(frozen=True)
class BreakdownGroup:
    key: str
    """``category:<id>`` / ``milestone:<id>`` / ``none`` / ``unassigned``。"""
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
    source: TimeSource
    time_zone: str
    groups: list[BreakdownGroup]
    periods: list[BreakdownPeriod]


@dataclass(frozen=True)
class ExportRow:
    """書き出しの 1 行（期間 × 日 × タスク）。タスク外は ``task_id`` が None。"""

    period: ReportPeriod
    work_date: date
    task_id: int | None
    task_title: str | None
    category_name: str | None
    milestone_name: str | None
    seconds: int


def _ratio(part: int, whole: int) -> float | None:
    if whole <= 0:
        return None
    return round(part / whole, 4)


__all__ = [
    "UNASSIGNED_GROUP",
    "UNGROUPED_GROUP",
    "Breakdown",
    "BreakdownGroup",
    "BreakdownGroupBy",
    "BreakdownPeriod",
    "ExportRow",
    "GanttActualDay",
    "GanttActualSpan",
    "PeriodComparison",
    "PeriodReport",
    "TaskActualsBoard",
    "TaskActualsRow",
    "TimeSource",
]
