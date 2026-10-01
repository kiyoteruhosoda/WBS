"""締め（task #161 / ADR-0011）の API スキーマ。"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from src.application.dto.closing_dto import (
    ClosingBoard,
    ClosingPeriodState,
    ClosingResult,
    DailyTaskTotal,
    OverlapFinding,
    PendingClosings,
)
from src.domain.value_objects.half_month_period import HalfMonthPeriod
from src.presentation.api.schemas.calendar_schemas import CalendarOccurrenceResponse
from src.presentation.api.schemas.time_entry_schemas import TimeEntryResponse
from src.presentation.api.schemas.types import UtcDatetime
from src.presentation.api.schemas.work_log_schemas import WorkLogResponse


class ClosingPeriodRangeResponse(BaseModel):
    first_day: dt.date = Field(description="初日（利用者のタイムゾーンの日付、含む）")
    last_day: dt.date = Field(description="末日（含む）")

    @classmethod
    def from_period(cls, period: HalfMonthPeriod) -> ClosingPeriodRangeResponse:
        return cls(first_day=period.first_day, last_day=period.last_day)


class ClosingPeriodResponse(ClosingPeriodRangeResponse):
    status: str = Field(description="`open`（未確定）か `closed`（確定済み）")
    time_zone: str = Field(description="区切りに使ったタイムゾーン（確定済みなら確定したときの値）")
    starts_at: UtcDatetime = Field(description="区切りの始まりの瞬間（含む）")
    ends_at: UtcDatetime = Field(description="区切りの終わりの瞬間（含まない）")
    closed_at: UtcDatetime | None

    @classmethod
    def from_state(cls, state: ClosingPeriodState) -> ClosingPeriodResponse:
        return cls(
            first_day=state.period.first_day,
            last_day=state.period.last_day,
            status="closed" if state.closed is not None else "open",
            time_zone=state.time_zone,
            starts_at=state.starts_at,
            ends_at=state.ends_at,
            closed_at=state.closed.closed_at if state.closed is not None else None,
        )


class DailyTaskTotalResponse(BaseModel):
    work_date: dt.date
    task_id: int | None
    task_title: str | None
    seconds: int = Field(description="丸めない長さ（秒）。日をまたぐ打刻は 0:00 で割ってある")

    @classmethod
    def from_total(cls, total: DailyTaskTotal) -> DailyTaskTotalResponse:
        return cls(
            work_date=total.work_date,
            task_id=total.task_id,
            task_title=total.task_title,
            seconds=total.seconds,
        )


class OverlapResponse(BaseModel):
    entry_ids: list[int] = Field(description="重なっている 2 本（始まりの早い順）")
    seconds: int

    @classmethod
    def from_finding(cls, finding: OverlapFinding) -> OverlapResponse:
        return cls(
            entry_ids=[finding.first_entry_id, finding.second_entry_id], seconds=finding.seconds
        )


class ClosingFindingsResponse(BaseModel):
    long_running_entry_ids: list[int] = Field(description="止め忘れ（12 時間超）")
    overlaps: list[OverlapResponse]
    unassigned_entry_ids: list[int] = Field(
        description="タスクが無い・消えた打刻。確定の前に振るか消す"
    )
    missed_occurrences: list[CalendarOccurrenceResponse] = Field(
        description="終わった予定の回のうち、掛かる打刻が 1 本も無いもの（終日は除く）"
    )
    count: int = Field(description="気付かせる物の数（画面の印のため）")


class ClosingBoardResponse(BaseModel):
    period: ClosingPeriodResponse
    entries: list[TimeEntryResponse] = Field(description="期間に掛かる打刻（始まりの順）")
    occurrences: list[CalendarOccurrenceResponse] = Field(
        description="期間の予定の回（利用者のタイムゾーンへ投影済み）"
    )
    daily_totals: list[DailyTaskTotalResponse] = Field(
        description="日ごと・タスクごとの合計（確定で作る work_logs と同じ割り方。走っている打刻は今まで）"
    )
    findings: ClosingFindingsResponse

    @classmethod
    def from_board(cls, board: ClosingBoard) -> ClosingBoardResponse:
        f = board.findings
        return cls(
            period=ClosingPeriodResponse.from_state(board.state),
            entries=[TimeEntryResponse.from_view(v) for v in board.entries],
            occurrences=[CalendarOccurrenceResponse.from_view(o) for o in board.occurrences],
            daily_totals=[DailyTaskTotalResponse.from_total(t) for t in board.daily_totals],
            findings=ClosingFindingsResponse(
                long_running_entry_ids=f.long_running_entry_ids,
                overlaps=[OverlapResponse.from_finding(o) for o in f.overlaps],
                unassigned_entry_ids=f.unassigned_entry_ids,
                missed_occurrences=[
                    CalendarOccurrenceResponse.from_view(o) for o in f.missed_occurrences
                ],
                count=(
                    len(f.long_running_entry_ids)
                    + len(f.overlaps)
                    + len(f.unassigned_entry_ids)
                    + len(f.missed_occurrences)
                ),
            ),
        )


class ClosingResultResponse(BaseModel):
    period: ClosingPeriodResponse
    work_logs: list[WorkLogResponse] = Field(description="確定で作った実績（source=closing）")

    @classmethod
    def from_result(cls, result: ClosingResult) -> ClosingResultResponse:
        return cls(
            period=ClosingPeriodResponse.from_state(result.state),
            work_logs=[
                WorkLogResponse.model_validate(w, from_attributes=True) for w in result.work_logs
            ],
        )


class ReopenResponse(BaseModel):
    first_day: dt.date
    removed_work_logs: int


class PendingClosingsResponse(BaseModel):
    has_pending: bool
    current: ClosingPeriodRangeResponse = Field(description="今の期間（利用者のタイムゾーン）")
    pending: list[ClosingPeriodRangeResponse] = Field(
        description="今の期間より前で確定していない期間（古い順。最初の打刻の期間から数える）"
    )

    @classmethod
    def from_pending(cls, pending: PendingClosings) -> PendingClosingsResponse:
        return cls(
            has_pending=bool(pending.pending),
            current=ClosingPeriodRangeResponse.from_period(pending.current),
            pending=[ClosingPeriodRangeResponse.from_period(p) for p in pending.pending],
        )
