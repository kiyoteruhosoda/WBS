from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.domain.value_objects.task_status import TaskStatus


class TaskCreateRequest(BaseModel):
    title: str
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)
    urgency: int = Field(default=3, ge=1, le=5)
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    urgency: int | None = Field(default=None, ge=1, le=5)
    status: TaskStatus | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None


class TaskResponse(BaseModel):
    id: int
    user_id: int
    title: str
    category_id: int | None = None
    priority: int
    urgency: int
    status: str
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: float | None = None
    remaining_hours: float | None = None
    actual_hours: float = 0.0
    progress_percent: float = 0.0
    priority_score: int = 0
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
