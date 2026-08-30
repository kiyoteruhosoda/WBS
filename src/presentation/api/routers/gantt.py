from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.gantt_use_cases import GanttUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep

router = APIRouter(prefix="/gantt", tags=["gantt"])


@router.get("")
def get_gantt(db: DbDep, current_user: CurrentUserDep) -> list[dict]:
    uc = GanttUseCases(db)
    return uc.get_gantt_data(current_user.user_id)
