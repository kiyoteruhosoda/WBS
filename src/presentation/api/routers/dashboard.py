from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.dashboard_use_cases import DashboardUseCases
from src.presentation.api.dependencies import DbDep
from src.presentation.api.schemas.dashboard_schemas import KpiResponse, TodayBucketsResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
USER_ID = 1


# 応答モデルを通さないと、タスクの時刻が Z 無しで出る（HANDOVER §14）。
@router.get("/today", response_model=TodayBucketsResponse)
def get_today_buckets(db: DbDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_today_buckets(USER_ID)


@router.get("/kpi", response_model=KpiResponse)
def get_kpi(db: DbDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_kpi(USER_ID)
