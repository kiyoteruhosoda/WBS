"""休み（WinTrack、task #392 / ADR-0048）。

``PUT /auto/{日付}`` は WinTrack がその日の自動の休みを丸ごと置き換える口、``GET ""`` は送れたかの確かめ。
どちらも assay のアクセストークンで叩ける（``AppOrWebUserDep``、ADR-0018）。表題やアプリ名は受け取らない。
休みは打刻を切り抜かず、実績の長さを出すときに重なる時間を引く。確定済みの締めの期間の日は 409（``closed``）。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from src.presentation.api.dependencies import AppOrWebUserDep, WorkBreakUseCasesDep
from src.presentation.api.schemas.work_break_schemas import (
    AutoWorkBreaksRequest,
    AutoWorkBreaksResponse,
    WorkBreakResponse,
    WorkBreaksResponse,
)
from src.shared.clock import to_naive_utc

router = APIRouter(prefix="/breaks", tags=["breaks"])


@router.put("/auto/{day}", response_model=AutoWorkBreaksResponse)
def replace_automatic_breaks(
    day: date,
    body: AutoWorkBreaksRequest,
    uc: WorkBreakUseCasesDep,
    current_user: AppOrWebUserDep,
) -> AutoWorkBreaksResponse:
    """その日（``time_zone`` での日付）の自動の休みを丸ごと置き換える（送り直しても同じ）。"""
    saved = uc.replace_automatic(
        current_user.user_id,
        day,
        body.time_zone,
        [(to_naive_utc(b.started_at), to_naive_utc(b.ended_at)) for b in body.breaks],
    )
    return AutoWorkBreaksResponse(date=day, breaks=[WorkBreakResponse.from_break(b) for b in saved])


@router.get("", response_model=WorkBreaksResponse)
def list_breaks(
    uc: WorkBreakUseCasesDep,
    current_user: AppOrWebUserDep,
    start: Annotated[AwareDatetime, Query(description="区間の始まり（含む）。オフセット付き")],
    end: Annotated[AwareDatetime, Query(description="区間の終わり（含まない）。オフセット付き")],
) -> WorkBreaksResponse:
    breaks = uc.list_in_period(current_user.user_id, to_naive_utc(start), to_naive_utc(end))
    return WorkBreaksResponse(breaks=[WorkBreakResponse.from_break(b) for b in breaks])
