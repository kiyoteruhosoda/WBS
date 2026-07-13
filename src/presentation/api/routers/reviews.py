from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from src.application.use_cases.review_use_cases import ReviewUseCases
from src.presentation.api.dependencies import DbDep

router = APIRouter(prefix="/reviews", tags=["reviews"])
USER_ID = 1


def _current_week() -> str:
    now = datetime.utcnow()
    return now.strftime("%G-W%V")


@router.get("/weekly")
def get_weekly_review(db: DbDep, week: str = Query(default_factory=_current_week)) -> dict:
    uc = ReviewUseCases(db)
    return uc.get_weekly_review(USER_ID, week)
