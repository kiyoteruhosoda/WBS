from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from src.domain.value_objects.task_status import TaskStatus

@dataclass
class Task:
    id: int | None
    user_id: int
    title: str
    category_id: int | None = None
    priority: int = 3
    urgency: int = 3
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    remaining_hours: Decimal | None = None
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
