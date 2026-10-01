from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.dashboard_use_cases import DashboardUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.dashboard_schemas import KpiResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
# 今日のタスクの束は「今日」の画面の要約（/api/today）へ寄せた（ADR-0015）。ここは KPI だけ。


@router.get("/kpi", response_model=KpiResponse)
def get_kpi(db: DbDep, current_user: CurrentUserDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_kpi(current_user.user_id)
