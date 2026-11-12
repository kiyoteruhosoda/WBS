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
    duration_seconds: int | None = None
    """Exact length (seconds) when created by a closing. ``hours`` is the value rounded to 2 decimals (ADR-0012)."""
    tracker_first_day: date | None = None
    """For rows received from Tracker: first day of Tracker's closing period (ADR-0056)."""

    @property
    def is_from_closing(self) -> bool:
        return self.source is WorkLogSource.CLOSING

    @property
    def seconds(self) -> int:
        """Length (seconds). Closing rows use the exact length; hand-written rows derive it from ``hours``."""
        if self.duration_seconds is not None:
            return self.duration_seconds
        return round(self.hours * 3600)
