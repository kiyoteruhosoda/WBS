from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.domain.value_objects.task_status import TaskStatus


@dataclass
class CreateTaskDTO:
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
    # Empty = unclassified. ⚠ A task with a parent goes into the parent's project (a different value is 422, ADR-0024)
    project_id: int | None = None
    # Assignee. If not sent, the creator (ADR-0055). Sending null means unassigned
    assignee_user_id: int | None = None
    assignee_user_id_given: bool = False
    # Allocation rate (%, may be empty, ADR-0058)
    allocation_percent: int | None = None

@dataclass
class UpdateTaskDTO:
    title: str | None = None
    category_id: int | None = None
    priority: int | None = None
    urgency: int | None = None
    status: TaskStatus | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    # Remaining can be reset to empty (empty = estimate - actual is used as the default), so keep "was it sent" separately
    remaining_hours: Decimal | None = None
    remaining_hours_given: bool = False
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # Milestone and project can be reset to empty, so keep "was it sent" separately
    milestone_id_given: bool = False
    project_id: int | None = None
    project_id_given: bool = False
    # Assignee can be reset to empty (ADR-0055)
    assignee_user_id: int | None = None
    assignee_user_id_given: bool = False
    # Allocation rate can be reset to empty (ADR-0058)
    allocation_percent: int | None = None
    allocation_percent_given: bool = False
