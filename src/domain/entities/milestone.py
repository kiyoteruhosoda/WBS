from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Milestone:
    id: int | None
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
