from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from src.domain.services.completion_forecast import ForecastGap
from src.domain.value_objects.task_status import TaskStatus
from src.presentation.api.schemas.types import UtcDatetime


class TaskCreateRequest(BaseModel):
    title: str
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)
    urgency: int = Field(default=3, ge=1, le=5)
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    # Manually kept remaining time (hours). Empty uses "estimate - actual" as the default (ADR-0010). Sending null on update clears it
    remaining_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # Empty = uncategorized. A task with a parent goes in the parent's project (omitted = same as the parent; a different value is 422. ADR-0024)
    project_id: int | None = None
    # Assignee (user id). Omitted = the creator, null = unassigned. 422 if not a member of the root project (ADR-0055)
    assignee_user_id: int | None = None
    # Allocation rate (%). If set, the forecast assumes this share of the assignee's free daily time. Empty = done in order (ADR-0058)
    allocation_percent: int | None = Field(default=None, ge=1, le=100)


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    urgency: int | None = Field(default=None, ge=1, le=5)
    status: TaskStatus | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    # Manually kept remaining time (hours). Empty uses "estimate - actual" as the default (ADR-0010). Sending null on update clears it
    remaining_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))
    memo: str | None = None
    parent_task_id: int | None = None
    # Sending null removes the milestone. One outside the project is 422 (ADR-0024)
    milestone_id: int | None = None
    # Sending null makes it uncategorized. Descendants move too. A child task sending a value different from its parent is 422
    project_id: int | None = None
    # Sending null unassigns. 422 if not a member of the root project (ADR-0055)
    assignee_user_id: int | None = None
    # Sending null removes the rate (done in order). ADR-0058
    allocation_percent: int | None = Field(default=None, ge=1, le=100)


class TaskMoveToProjectRequest(BaseModel):
    """Move the selected tasks to another project together. Sending ``null`` as ``project_id`` makes them uncategorized (ADR-0030)."""

    task_ids: list[int] = Field(min_length=1, max_length=500)
    project_id: int | None


class TaskMoveToProjectResponse(BaseModel):
    # Tasks whose project changed (the selected roots and the descendants that moved with them). Ones already there are not included
    moved_task_ids: list[int]
    # Tasks whose milestone was removed because it became out of reach
    detached_milestone_task_ids: list[int]


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
    # Own remaining time (manual value, or estimate - actual if empty; 0 for DONE), and the manually entered value itself
    remaining_hours: float | None = None
    remaining_hours_entered: float | None = None
    # Own actual time (sum of work_logs)
    actual_hours: float = 0.0
    has_subtasks: bool = False
    # Actual and remaining used in the progress formula (rolled up over self and all descendants if it has children)
    rollup_actual_hours: float = 0.0
    rollup_remaining_hours: float | None = None
    # actual / (actual + remaining) x 100. 100 for DONE. null when the denominator is 0 or remaining is undetermined
    progress_percent: float | None = None
    priority_score: int = 0
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # The project it belongs to (null = uncategorized) and the display path ("parent / child")
    project_id: int | None = None
    project_path: str | None = None
    # Assignee and their display name (ADR-0055). null if unassigned
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    # Allocation rate (%, ADR-0058). null means no rate
    allocation_percent: int | None = None
    # Expected finish (ADR-0058; computed on every read by stacking the remaining time on the assignee's free time). If not given, forecast_gap holds the reason
    forecast_start: date | None = None
    forecast_finish: date | None = None
    forecast_gap: ForecastGap | None = None
    # Calendar days by which the expected finish passes the due date (0 if it does not)
    forecast_overdue_days: int = 0
    completed_at: UtcDatetime | None = None
    deleted_at: UtcDatetime | None = None
    # When it was archived (ADR-0046). Archived tasks are not listed, but are returned when fetched individually
    archived_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}


class TaskRemovalResponse(BaseModel):
    """What deleting the task would do (shown in the confirmation dialog. ADR-0046).

    ``action`` is ``delete`` (no confirmed actuals) or ``archive`` (there are some; archive instead of deleting).
    """

    task_id: int
    title: str
    action: str
    work_log_hours: float
    archived: bool
