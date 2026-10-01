from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.application.use_cases.gantt_use_cases import GanttUseCases
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.presentation.api.dependencies import CurrentUserDep, DbDep

router = APIRouter(prefix="/gantt", tags=["gantt"])


@router.get("")
def get_gantt(
    db: DbDep,
    current_user: CurrentUserDep,
    project_id: Annotated[
        int | None, Query(description="このプロジェクトと、その子孫のプロジェクトのタスクだけ")
    ] = None,
) -> list[dict]:
    uc = GanttUseCases(
        tasks=SqlAlchemyTaskRepository(db),
        dependencies=SqlAlchemyTaskDependencyRepository(db),
        projects=SqlAlchemyProjectRepository(db),
    )
    return uc.get_gantt_data(current_user.user_id, project_id)
