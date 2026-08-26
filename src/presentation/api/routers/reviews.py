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
    # 形の検査はここ。読めない値が strptime まで届くと 500 になる。
    week: str | None = Query(default=None, pattern=r"^\d{4}-W\d{2}$"),
) -> dict:
    uc = ReviewUseCases(db)
    return uc.get_weekly_review(USER_ID, week)
