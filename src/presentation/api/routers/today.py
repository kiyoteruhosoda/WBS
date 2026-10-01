"""「今日」の画面（task #160 / ADR-0015）。"""

from __future__ import annotations

from fastapi import APIRouter

from src.presentation.api.dependencies import CurrentUserDep, TodayUseCasesDep
from src.presentation.api.schemas.today_schemas import TodaySummaryResponse

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodaySummaryResponse)
def get_today_summary(uc: TodayUseCasesDep, current_user: CurrentUserDep) -> TodaySummaryResponse:
    """利用者のタイムゾーンでの今日: 打刻・実績・まだ予定を取っていないタスク。"""
    return TodaySummaryResponse.from_summary(uc.summary(current_user.user_id))
