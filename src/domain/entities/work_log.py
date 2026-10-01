from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.value_objects.work_log_source import WorkLogSource


@dataclass
class WorkLog:
    id: int | None
    user_id: int
    task_id: int
    work_date: date
    hours: Decimal
    memo: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source: WorkLogSource = WorkLogSource.MANUAL
    closing_period_id: int | None = None
    """締めで作ったとき、どの期間から作ったか（開け直しで消すため）。"""
    duration_seconds: int | None = None
    """締めで作ったときの正確な長さ（秒）。``hours`` は小数 2 桁に収めた値（ADR-0011）。"""

    @property
    def is_from_closing(self) -> bool:
        return self.source is WorkLogSource.CLOSING
