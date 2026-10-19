"""打刻まわりを Tracker へ移したか（task #526 / ADR-0053）。

ログインの前でも読める（設定の値だけで、利用者のものは何も無い。画面は起動のたびに読む）。
"""

from __future__ import annotations

from fastapi import APIRouter

from src.presentation.api.dependencies import TrackerMoveSettingsDep
from src.presentation.api.schemas.tracker_move_schemas import TrackerMoveResponse

router = APIRouter(prefix="/tracker-move", tags=["tracker-move"])


@router.get("", response_model=TrackerMoveResponse)
def get_tracker_move(settings: TrackerMoveSettingsDep) -> TrackerMoveResponse:
    return TrackerMoveResponse(mode=settings.phase.value, url=settings.public_url)
