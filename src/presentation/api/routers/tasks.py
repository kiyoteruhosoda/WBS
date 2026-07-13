from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.application.use_cases.task_use_cases import TaskUseCases
from src.presentation.api.dependencies import DbDep
from src.presentation.api.schemas.task_schemas import (
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
USER_ID = 1


def get_use_case(db: DbDep) -> TaskUseCases:
    return TaskUseCases(db)


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    db: DbDep,
    status_filter: str | None = None,
    category_id: int | None = None,
    milestone_id: int | None = None,
    parent_task_id: int | None = None,
) -> list[TaskResponse]:
    uc = get_use_case(db)
    filters = {}
    if status_filter:
        filters["status"] = status_filter
    if category_id is not None:
        filters["category_id"] = category_id
    if milestone_id is not None:
        filters["milestone_id"] = milestone_id
    if parent_task_id is not None:
        filters["parent_task_id"] = parent_task_id
    return [TaskResponse(**t) for t in uc.list_tasks(USER_ID, filters)]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreateRequest, db: DbDep) -> TaskResponse:
    uc = get_use_case(db)
    dto = CreateTaskDTO(
        user_id=USER_ID,
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
    )
    return TaskResponse(**uc.create_task(dto))


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: DbDep) -> TaskResponse:
    uc = get_use_case(db)
    return TaskResponse(**uc.get_task(task_id, USER_ID))


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, body: TaskUpdateRequest, db: DbDep) -> TaskResponse:
    uc = get_use_case(db)
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
        memo=body.memo,
        parent_task_id=body.parent_task_id,
        milestone_id=body.milestone_id,
    )
    return TaskResponse(**uc.update_task(task_id, USER_ID, dto))


@router.patch("/{task_id}", response_model=TaskResponse)
def patch_task(task_id: int, body: TaskUpdateRequest, db: DbDep) -> TaskResponse:
    return update_task(task_id, body, db)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: DbDep) -> None:
    uc = get_use_case(db)
    uc.delete_task(task_id, USER_ID)
