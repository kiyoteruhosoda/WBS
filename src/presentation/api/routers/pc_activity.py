"""PC を使っていた時間（WinTrack → wbstimer、task #397 / ADR-0049）。

``PUT /{日付}`` は WinTrack がその日の区間を丸ごと置き換える口、``GET ""`` は wbstimer が開始・終了を押したときに読む口。
どちらも assay のアクセストークンで叩ける（``AppOrWebUserDep``、ADR-0018）。表題やアプリ名は受け取らない。
打刻・実績・締めには使わないので、確定済みの締めの期間の日でも受ける。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from src.presentation.api.dependencies import AppOrWebUserDep, PcActivityUseCasesDep
from src.presentation.api.schemas.pc_activity_schemas import (
    PcActivityDayRequest,
    PcActivityDayResponse,
    PcActivityResponse,
    PcActivitySpanResponse,
)
from src.shared.clock import to_naive_utc

router = APIRouter(prefix="/pc-activity", tags=["pc-activity"])


@router.put("/{day}", response_model=PcActivityDayResponse)
def replace_pc_activity_day(
    day: date,
    body: PcActivityDayRequest,
    uc: PcActivityUseCasesDep,
    current_user: AppOrWebUserDep,
) -> PcActivityDayResponse:
    """その日（``time_zone`` での日付）の区間を丸ごと置き換える（送り直しても同じ）。"""
    saved = uc.replace_day(
        current_user.user_id,
        day,
        body.time_zone,
        [(to_naive_utc(s.started_at), to_naive_utc(s.ended_at)) for s in body.spans],
    )
    return PcActivityDayResponse(
        date=day,
        spans=[PcActivitySpanResponse.from_span(s) for s in saved.spans],
        updated_at=saved.updated_at,
    )


@router.get("", response_model=PcActivityResponse)
def list_pc_activity(
    uc: PcActivityUseCasesDep,
    current_user: AppOrWebUserDep,
    start: Annotated[AwareDatetime, Query(description="区間の始まり（含む）。オフセット付き")],
    end: Annotated[AwareDatetime, Query(description="区間の終わり（含まない）。オフセット付き")],
) -> PcActivityResponse:
    found = uc.list_in_period(current_user.user_id, to_naive_utc(start), to_naive_utc(end))
    return PcActivityResponse(
        spans=[PcActivitySpanResponse.from_span(s) for s in found.spans],
        updated_at=found.updated_at,
    )
