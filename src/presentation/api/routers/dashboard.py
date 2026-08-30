from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.dashboard_use_cases import DashboardUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.dashboard_schemas import KpiResponse, TodayBucketsResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# 応答モデルを通さないと、タスクの時刻が Z 無しで出る（HANDOVER §14）。
@router.get("/today", response_model=TodayBucketsResponse)
def get_today_buckets(db: DbDep, current_user: CurrentUserDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_today_buckets(current_user.user_id)


@router.get("/kpi", response_model=KpiResponse)
def get_kpi(db: DbDep, current_user: CurrentUserDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_kpi(current_user.user_id)
