from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.use_cases.dependency_use_cases import DependencyUseCases
from src.domain.value_objects.dependency_type import DependencyType
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.dependency_schemas import (
    DependencyCreateRequest,
    DependencyResponse,
    TaskDependenciesResponse,
)

router = APIRouter(prefix="/tasks", tags=["dependencies"])


def get_use_case(db: DbDep) -> DependencyUseCases:
    return DependencyUseCases(
        dependencies=SqlAlchemyTaskDependencyRepository(db),
        tasks=SqlAlchemyTaskRepository(db),
    )

UseCaseDep = Annotated[DependencyUseCases, Depends(get_use_case)]


@router.get("/{task_id}/dependencies", response_model=TaskDependenciesResponse)
def get_dependencies(task_id: int, uc: UseCaseDep, current_user: CurrentUserDep) -> TaskDependenciesResponse:
    data = uc.get_dependencies(task_id, current_user.user_id)
    return TaskDependenciesResponse(
        task_id=data["task_id"],
        predecessors=[DependencyResponse(**p) for p in data["predecessors"]],
        successors=[DependencyResponse(**s) for s in data["successors"]],
    )


@router.post("/{task_id}/dependencies", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
def add_dependency(task_id: int, body: DependencyCreateRequest, uc: UseCaseDep, current_user: CurrentUserDep) -> DependencyResponse:
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
def remove_dependency(task_id: int, predecessor_id: int, uc: UseCaseDep, current_user: CurrentUserDep) -> None:
    uc.remove_dependency(successor_task_id=task_id, predecessor_task_id=predecessor_id, user_id=current_user.user_id)
