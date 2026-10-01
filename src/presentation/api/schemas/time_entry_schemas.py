from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field

from src.application.dto.time_entry_dto import TimeEntryView
from src.presentation.api.schemas.types import UtcDatetime


class StartTimeEntryRequest(BaseModel):
    """Start。本文は空でよい。

    ``task_id`` を**送らなければ**既定の順（いまの予定のタスク → 直前の打刻のタスク → 未割当）で
    決める。``null`` を送ると未割当で始める。
    """

    task_id: int | None = None
    memo: str | None = Field(default=None, max_length=2000)


class TimeEntryUpdateRequest(BaseModel):
    """1 件の修正（締めの画面から）。送った欄だけを変える。

    時刻はオフセット付き（``Z`` か ``+09:00``）で送る。``ended_at`` に ``null`` は送れない
    （止まった打刻を走っている状態へは戻さない）。
    """

    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    task_id: int | None = None
    memo: str | None = Field(default=None, max_length=2000)


class TimeEntryResponse(BaseModel):
    id: int
    user_id: int
    task_id: int | None
    task_title: str | None
    started_at: UtcDatetime
    ended_at: UtcDatetime | None
    memo: str | None
    source: str
    is_running: bool
    duration_seconds: int
    is_long_running: bool
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_view(cls, view: TimeEntryView) -> TimeEntryResponse:
        e = view.entry
        assert e.id is not None
        return cls(
            id=e.id,
            user_id=e.user_id,
            task_id=e.task_id,
            task_title=view.task_title,
            started_at=e.started_at,
            ended_at=e.ended_at,
            memo=e.memo,
            source=e.source.value,
            is_running=e.is_running,
            duration_seconds=view.duration_seconds,
            is_long_running=view.is_long_running,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )


class CurrentTimeEntryResponse(BaseModel):
    """いま走っている打刻（無ければ ``entry`` は null）。

    ``server_now`` は経過時間を数える起点。端末の時計がずれていても、
    ``server_now - started_at`` を足し込めば経過が合う。
    """

    entry: TimeEntryResponse | None
    server_now: UtcDatetime


class StartTimeEntryResponse(BaseModel):
    started: TimeEntryResponse
    # 走っていた打刻を止めて切り替えたときの、止めた方
    stopped: TimeEntryResponse | None
    server_now: UtcDatetime


class StopTimeEntryResponse(BaseModel):
    # 走っていなかったときは null（Stop は何度押しても同じ結果）
    stopped: TimeEntryResponse | None
    server_now: UtcDatetime
