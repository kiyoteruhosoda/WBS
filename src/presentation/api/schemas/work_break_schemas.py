from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, Field

from src.domain.entities.work_break import WorkBreak
from src.presentation.api.schemas.types import UtcDatetime


class WorkBreakSpan(BaseModel):
    started_at: AwareDatetime
    ended_at: AwareDatetime


class AutoWorkBreaksRequest(BaseModel):
    """その日の自動の休み（WinTrack、ADR-0048）。``time_zone`` での日付。``breaks: []`` で全部消える。

    区間はその日の中に収まり・重ならず・``ended_at`` > ``started_at``（違えば 422）。
    """

    time_zone: str = Field(min_length=1, max_length=64)
    breaks: list[WorkBreakSpan] = Field(max_length=200)


class WorkBreakResponse(BaseModel):
    id: int
    started_at: UtcDatetime
    ended_at: UtcDatetime
    source: str

    @classmethod
    def from_break(cls, work_break: WorkBreak) -> WorkBreakResponse:
        assert work_break.id is not None
        return cls(
            id=work_break.id,
            started_at=work_break.started_at,
            ended_at=work_break.ended_at,
            source=work_break.source.value,
        )


class AutoWorkBreaksResponse(BaseModel):
    date: date
    breaks: list[WorkBreakResponse]


class WorkBreaksResponse(BaseModel):
    """``[start, end)`` に掛かる休み（始まりの順）。"""

    breaks: list[WorkBreakResponse]
