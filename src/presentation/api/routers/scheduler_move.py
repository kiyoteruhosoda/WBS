"""予定まわりを Scheduler へ移したか（task #535 / WBS の ADR-0054）。

ログインの前でも読める（設定の値だけで、利用者のものは何も無い。画面は起動のたびに読む）。
"""

from __future__ import annotations

from fastapi import APIRouter

from src.presentation.api.dependencies import SchedulerMoveSettingsDep
from src.presentation.api.schemas.scheduler_move_schemas import SchedulerMoveResponse

router = APIRouter(prefix="/scheduler-move", tags=["scheduler-move"])


@router.get("", response_model=SchedulerMoveResponse)
def get_scheduler_move(settings: SchedulerMoveSettingsDep) -> SchedulerMoveResponse:
    return SchedulerMoveResponse(mode=settings.phase.value, url=settings.public_url)
