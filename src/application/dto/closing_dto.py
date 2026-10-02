"""締め（task #161 / ADR-0012）のユースケースが返す形。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.application.dto.calendar_event_dto import OccurrenceView
from src.application.dto.time_entry_dto import TimeEntryView
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.work_log import WorkLog
from src.domain.value_objects.half_month_period import HalfMonthPeriod


@dataclass(frozen=True)
class DailyTaskTotal:
    """日ごと・タスクごとの合計（確定で作る ``work_logs`` と同じ割り方。丸めない）。"""

    work_date: date
    task_id: int | None
    task_title: str | None
    seconds: int
    project_id: int | None = None
    """タスクのいまのプロジェクト（未割当・消えたタスク・未分類は None。task #189）。"""


@dataclass(frozen=True)
class OverlapFinding:
    first_entry_id: int
    second_entry_id: int
    seconds: int


@dataclass(frozen=True)
class ClosingFindings:
    """気付かせる物（期間の要約）。"""

    long_running_entry_ids: list[int]
    """止め忘れ（12 時間超）。"""
    overlaps: list[OverlapFinding]
    unassigned_entry_ids: list[int]
    """タスクが無い・消えた打刻（確定の前に振るか消す）。"""
    missed_occurrences: list[OccurrenceView]
    """終わった予定の回のうち、掛かる打刻が 1 本も無いもの（終日の回は除く）。"""


@dataclass(frozen=True)
class ClosingPeriodState:
    period: HalfMonthPeriod
    time_zone: str
    starts_at: datetime
    """区切りの瞬間（naive な UTC）。確定済みなら確定したときの値。"""
    ends_at: datetime
    closed: ClosingPeriod | None
    """確定済みならその行。未確定なら None。"""


@dataclass(frozen=True)
class ClosingBoard:
    """締めの画面 1 枚分: 期間の打刻・予定の回・合計・気付かせる物。"""

    state: ClosingPeriodState
    entries: list[TimeEntryView]
    occurrences: list[OccurrenceView]
    daily_totals: list[DailyTaskTotal]
    findings: ClosingFindings


@dataclass(frozen=True)
class ClosingResult:
    state: ClosingPeriodState
    work_logs: list[WorkLog]


@dataclass(frozen=True)
class PendingClosings:
    """今の期間より前で、まだ確定していない期間（画面の上部の知らせ）。"""

    current: HalfMonthPeriod
    pending: list[HalfMonthPeriod]
