from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class CreateWorkLogDTO:
    user_id: int
    task_id: int
    work_date: date
    hours: Decimal
    memo: str | None = None

@dataclass
class UpdateWorkLogDTO:
    work_date: date | None = None
    hours: Decimal | None = None
    memo: str | None = None
