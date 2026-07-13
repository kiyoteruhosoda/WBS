from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.dashboard_use_cases import DashboardUseCases
from src.presentation.api.dependencies import DbDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
USER_ID = 1


@router.get("/today")
def get_today_buckets(db: DbDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_today_buckets(USER_ID)


@router.get("/kpi")
def get_kpi(db: DbDep) -> dict:
    uc = DashboardUseCases(db)
    return uc.get_kpi(USER_ID)
