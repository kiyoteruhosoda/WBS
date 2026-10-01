from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.gantt_use_cases import GanttUseCases
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.presentation.api.dependencies import CurrentUserDep, DbDep

router = APIRouter(prefix="/gantt", tags=["gantt"])


@router.get("")
def get_gantt(db: DbDep, current_user: CurrentUserDep) -> list[dict]:
    uc = GanttUseCases(
        tasks=SqlAlchemyTaskRepository(db),
        dependencies=SqlAlchemyTaskDependencyRepository(db),
    )
    return uc.get_gantt_data(current_user.user_id)
