from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


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
