from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, Field

from src.domain.entities.pc_activity import PcActivitySpan
from src.presentation.api.schemas.types import UtcDatetime


class PcActivitySpanRequest(BaseModel):
    started_at: AwareDatetime
    ended_at: AwareDatetime


class PcActivityDayRequest(BaseModel):
    """その日に PC を使っていた区間（WinTrack、ADR-0049）。``time_zone`` での日付。``spans: []`` で全部消える。

    区間はその日の中に収まり・重ならず・``ended_at`` > ``started_at``（違えば 422）。
    """

    time_zone: str = Field(min_length=1, max_length=64)
    spans: list[PcActivitySpanRequest] = Field(max_length=500)


class PcActivitySpanResponse(BaseModel):
    started_at: UtcDatetime
    ended_at: UtcDatetime

    @classmethod
    def from_span(cls, span: PcActivitySpan) -> PcActivitySpanResponse:
        return cls(started_at=span.started_at, ended_at=span.ended_at)


class PcActivityDayResponse(BaseModel):
    date: date
    spans: list[PcActivitySpanResponse]
    updated_at: UtcDatetime
    """WBS がこの日を受けた時刻。"""


class PcActivityResponse(BaseModel):
    """``[start, end)`` に掛かる区間（始まりの順）。``updated_at`` は範囲の日のうち最後に受けた時刻。"""

    spans: list[PcActivitySpanResponse]
    updated_at: UtcDatetime | None
