from __future__ import annotations

from fastapi import APIRouter, status

from src.application.use_cases.dependency_use_cases import DependencyUseCases
from src.domain.value_objects.dependency_type import DependencyType
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.dependency_schemas import (
    DependencyCreateRequest,
    DependencyResponse,
    TaskDependenciesResponse,
)

router = APIRouter(prefix="/tasks", tags=["dependencies"])


@router.get("/{task_id}/dependencies", response_model=TaskDependenciesResponse)
def get_dependencies(task_id: int, db: DbDep, current_user: CurrentUserDep) -> TaskDependenciesResponse:
    uc = DependencyUseCases(db)
    data = uc.get_dependencies(task_id, current_user.user_id)
    return TaskDependenciesResponse(
        task_id=data["task_id"],
        predecessors=[DependencyResponse(**p) for p in data["predecessors"]],
        successors=[DependencyResponse(**s) for s in data["successors"]],
    )


@router.post("/{task_id}/dependencies", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
def add_dependency(task_id: int, body: DependencyCreateRequest, db: DbDep, current_user: CurrentUserDep) -> DependencyResponse:
    uc = DependencyUseCases(db)
    dep = uc.add_dependency(
        successor_task_id=task_id,
        predecessor_task_id=body.predecessor_task_id,
        user_id=current_user.user_id,
        dependency_type=body.dependency_type.value,
        lag_days=body.lag_days,
    )
    return DependencyResponse(
        predecessor_task_id=dep.predecessor_task_id,
        successor_task_id=dep.successor_task_id,
        dependency_type=dep.dependency_type.value if isinstance(dep.dependency_type, DependencyType) else dep.dependency_type,
        lag_days=dep.lag_days,
        created_at=dep.created_at,
    )


@router.delete("/{task_id}/dependencies/{predecessor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_dependency(task_id: int, predecessor_id: int, db: DbDep, current_user: CurrentUserDep) -> None:
    uc = DependencyUseCases(db)
    uc.remove_dependency(successor_task_id=task_id, predecessor_task_id=predecessor_id, user_id=current_user.user_id)
