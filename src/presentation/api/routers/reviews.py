from __future__ import annotations

from fastapi import APIRouter, Query

from src.application.use_cases.review_use_cases import ReviewUseCases
from src.presentation.api.dependencies import DbDep

router = APIRouter(prefix="/reviews", tags=["reviews"])
USER_ID = 1


@router.get("/weekly")
def get_weekly_review(
    db: DbDep,
    # 既定の週は利用者のタイムゾーンで決める（UserClock）。UTC の「今」から求めると、
    # JST の利用者にとって月曜 0:00〜9:00 のあいだ前の週が開く。
    week: str | None = Query(default=None),
) -> dict:
    uc = ReviewUseCases(db)
    return uc.get_weekly_review(USER_ID, week)
