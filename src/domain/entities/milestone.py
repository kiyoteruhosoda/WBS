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
    # Owning project (empty = unclassified; can be attached to any task. ADR-0024)
    project_id: int | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
