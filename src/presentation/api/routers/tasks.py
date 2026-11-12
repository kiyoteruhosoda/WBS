from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.presentation.api.dependencies import (
    CurrentUserDep,
    TaskRemovalUseCasesDep,
    TaskUseCasesDep,
)
from src.presentation.api.schemas.task_schemas import (
    TaskCreateRequest,
    TaskMoveToProjectRequest,
    TaskMoveToProjectResponse,
    TaskRemovalResponse,
    TaskResponse,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    uc: TaskUseCasesDep,
    current_user: CurrentUserDep,
    status_filter: str | None = None,
    category_id: int | None = None,
    milestone_id: int | None = None,
    parent_task_id: int | None = None,
    project_id: Annotated[
        int | None, Query(description="Only tasks in this project and its descendant projects")
    ] = None,
    unclassified: Annotated[
        bool, Query(description="If true, only tasks without a project (uncategorized)")
    ] = False,
    assignee: Annotated[
        str | None,
        Query(
            description="Filter by assignee: `me` (yourself), `none` (unassigned), or a user id (ADR-0055)",
            pattern=r"^(me|none|[0-9]+)$",
        ),
    ] = None,
) -> list[TaskResponse]:
    filters: dict = {}
    if status_filter:
        filters["status"] = status_filter
    if category_id is not None:
        filters["category_id"] = category_id
    if milestone_id is not None:
        filters["milestone_id"] = milestone_id
    if parent_task_id is not None:
        filters["parent_task_id"] = parent_task_id
    if project_id is not None:
        filters["project_id"] = project_id
    if unclassified:
        filters["unclassified"] = True
    if assignee == "me":
        filters["assignee_user_id"] = current_user.user_id
    elif assignee == "none":
        filters["unassigned"] = True
    elif assignee is not None:
        filters["assignee_user_id"] = int(assignee)
    return [
        TaskResponse(**t)
        for t in uc.list_tasks(current_user.user_id, filters)
    ]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreateRequest, uc: TaskUseCasesDep, current_user: CurrentUserDep) -> TaskResponse:
    dto = CreateTaskDTO(
        user_id=current_user.user_id,
        title=body.title,
        category_id=body.category_id,
        priority=body.priority,
        urgency=body.urgency,
        status=body.status,
        start_date=body.start_date,
        due_date=body.due_date,
        estimated_hours=body.estimated_hours,
        remaining_hours=body.remaining_hours,
        memo=body.memo,
        parent_task_id=body.parent_task_id,
        milestone_id=body.milestone_id,
        project_id=body.project_id,
        assignee_user_id=body.assignee_user_id,
        assignee_user_id_given="assignee_user_id" in body.model_fields_set,
        allocation_percent=body.allocation_percent,
    )
    return TaskResponse(**uc.create_task(dto))


@router.post("/move-to-project", response_model=TaskMoveToProjectResponse)
def move_tasks_to_project(
    body: TaskMoveToProjectRequest, uc: TaskUseCasesDep, current_user: CurrentUserDep
) -> TaskMoveToProjectResponse:
    """Move the selected tasks to another project together (``null`` makes them uncategorized).

    Descendants move with their root. If the selection includes a child task whose ancestor is not also selected, nothing changes and 422 is returned (ADR-0024, ADR-0030).
    """
    result = uc.move_to_project(current_user.user_id, body.task_ids, body.project_id)
    return TaskMoveToProjectResponse(**result)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, uc: TaskUseCasesDep, current_user: CurrentUserDep) -> TaskResponse:
    return TaskResponse(**uc.get_task(task_id, current_user.user_id))


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, body: TaskUpdateRequest, uc: TaskUseCasesDep, current_user: CurrentUserDep) -> TaskResponse:
    dto = UpdateTaskDTO(
        title=body.title,
        category_id=body.category_id,
        priority=body.priority,
        urgency=body.urgency,
        status=body.status,
        start_date=body.start_date,
        due_date=body.due_date,
        estimated_hours=body.estimated_hours,
        remaining_hours=body.remaining_hours,
        remaining_hours_given="remaining_hours" in body.model_fields_set,
        memo=body.memo,
        parent_task_id=body.parent_task_id,
        milestone_id=body.milestone_id,
        milestone_id_given="milestone_id" in body.model_fields_set,
        project_id=body.project_id,
        project_id_given="project_id" in body.model_fields_set,
        assignee_user_id=body.assignee_user_id,
        assignee_user_id_given="assignee_user_id" in body.model_fields_set,
        allocation_percent=body.allocation_percent,
        allocation_percent_given="allocation_percent" in body.model_fields_set,
    )
    return TaskResponse(**uc.update_task(task_id, current_user.user_id, dto))


@router.patch("/{task_id}", response_model=TaskResponse)
def patch_task(task_id: int, body: TaskUpdateRequest, uc: TaskUseCasesDep, current_user: CurrentUserDep) -> TaskResponse:
    return update_task(task_id, body, uc, current_user)


@router.get("/{task_id}/removal", response_model=TaskRemovalResponse)
def preview_task_removal(
    task_id: int, uc: TaskRemovalUseCasesDep, current_user: CurrentUserDep
) -> TaskRemovalResponse:
    """What deleting would do (confirmed actuals, and whether to delete or archive). ADR-0046."""
    preview = uc.preview(task_id, current_user.user_id)
    return TaskRemovalResponse(
        task_id=preview.task_id,
        title=preview.title,
        action=preview.action.value,
        work_log_hours=preview.work_log_hours,
        archived=preview.archived,
    )


@router.post("/{task_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_task(task_id: int, uc: TaskRemovalUseCasesDep, current_user: CurrentUserDep) -> None:
    """Archive (no longer shown in lists or as a move target; stays in the actuals table)."""
    uc.archive(task_id, current_user.user_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, uc: TaskRemovalUseCasesDep, current_user: CurrentUserDep) -> None:
    """Delete. 409 if there are confirmed actuals (archive instead)."""
    uc.delete(task_id, current_user.user_id)
