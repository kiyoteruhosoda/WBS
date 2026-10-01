"""締め（月 2 回の補正と確定。task #161 / ADR-0012）。

- ``GET /closing-periods/pending``: 今の期間より前で確定していない期間（画面の上部の知らせ）
- ``GET /closing-periods/{first_day}``: 締めの画面 1 枚分（打刻・予定の回・合計・気付かせる物）
- ``POST /closing-periods/{first_day}/close``: 確定（打刻から work_logs を作る）
- ``POST /closing-periods/{first_day}/reopen``: 開け直し（締めで作った work_logs を消す）

期間は初日（1 日か 16 日）で指す。区切りは利用者のタイムゾーン（設定）の 0:00。
打刻の補正（分割・結合・まとめてタスクを振る・予定の回から作る・手で足す）は ``/time-entries``。
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

from src.presentation.api.dependencies import ClosingUseCasesDep, CurrentUserDep
from src.presentation.api.schemas.closing_schemas import (
    ClosingBoardResponse,
    ClosingResultResponse,
    PendingClosingsResponse,
    ReopenResponse,
)

router = APIRouter(prefix="/closing-periods", tags=["closing-periods"])


@router.get("/pending", response_model=PendingClosingsResponse)
def get_pending_closings(
    uc: ClosingUseCasesDep, current_user: CurrentUserDep
) -> PendingClosingsResponse:
    return PendingClosingsResponse.from_pending(
        uc.pending(current_user.user_id, current_user.timezone)
    )


@router.get("/{first_day}", response_model=ClosingBoardResponse)
def get_closing_board(
    first_day: dt.date, uc: ClosingUseCasesDep, current_user: CurrentUserDep
) -> ClosingBoardResponse:
    return ClosingBoardResponse.from_board(
        uc.board(current_user.user_id, first_day, current_user.timezone)
    )


@router.post("/{first_day}/close", response_model=ClosingResultResponse)
def close_period(
    first_day: dt.date, uc: ClosingUseCasesDep, current_user: CurrentUserDep
) -> ClosingResultResponse:
    """確定。走っている打刻・未割当の打刻が期間に掛かっていれば 409。"""
    return ClosingResultResponse.from_result(
        uc.close(current_user.user_id, first_day, current_user.timezone)
    )


@router.post("/{first_day}/reopen", response_model=ReopenResponse)
def reopen_period(
    first_day: dt.date, uc: ClosingUseCasesDep, current_user: CurrentUserDep
) -> ReopenResponse:
    """開け直し（本人ができる）。確定していなければ 409。"""
    removed = uc.reopen(current_user.user_id, first_day)
    return ReopenResponse(first_day=first_day, removed_work_logs=removed)
