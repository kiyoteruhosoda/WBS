from __future__ import annotations
from fastapi import APIRouter
from src.application.use_cases.gantt_use_cases import GanttUseCases
from src.presentation.api.dependencies import DbDep

router = APIRouter(prefix="/gantt", tags=["gantt"])
USER_ID = 1


@router.get("")
def get_gantt(db: DbDep) -> list[dict]:
    uc = GanttUseCases(db)
    return uc.get_gantt_data(USER_ID)
