from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from src.application.dto.time_entry_dto import AutoTimeEntryOutcome, TimeEntryView
from src.presentation.api.schemas.types import UtcDatetime


class StartTimeEntryRequest(BaseModel):
    """Start。本文は空でよい。

    ``task_id`` を**送らなければ**既定の順（いまの予定のタスク → 直前の打刻のタスク → 未割当）で
    決める。``null`` を送ると未割当で始める。

    ``at`` は押した時刻（オフセット付き。ADR-0018）。アプリが電波の無いときに溜めた押下を
    送るときに付ける。送らなければ「今」。未来（60 秒を超えるずれ）と 7 日より前は 422。
    走っている打刻と同じ時刻なら送り直しとみなして何もしない。
    """

    task_id: int | None = None
    memo: str | None = Field(default=None, max_length=2000)
    at: AwareDatetime | None = None


class StopTimeEntryRequest(BaseModel):
    """Stop。本文は空でよい。``at`` は押した時刻（Start と同じ規則。ADR-0018）。"""

    at: AwareDatetime | None = None


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
    # 自動の打刻の送り方（fill / override）。自動の打刻でなければ null（ADR-0045）
    auto_mode: str | None = None
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
            auto_mode=e.auto_mode.value if e.auto_mode is not None else None,
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


class TimeEntryCreateRequest(BaseModel):
    """空き時間に打刻を足す（締めの画面から。``source=manual``）。時刻はオフセット付き。"""

    started_at: AwareDatetime
    ended_at: AwareDatetime
    task_id: int | None = None
    memo: str | None = Field(default=None, max_length=2000)


class TimeEntrySplitRequest(BaseModel):
    """``at`` で 2 本に分ける。``at`` は打刻の始まりと終わり（走っていれば今）の間。"""

    at: AwareDatetime


class TimeEntrySplitResponse(BaseModel):
    first: TimeEntryResponse
    second: TimeEntryResponse


class TimeEntryMergeRequest(BaseModel):
    """打刻をつなぐ（2 本以上）。``task_id`` を送らなければ、早い方から最初に見つかったタスク。"""

    entry_ids: list[int] = Field(min_length=2, max_length=500)
    task_id: int | None = None


class TimeEntryAssignRequest(BaseModel):
    """まとめてタスクを振る。``task_id`` に ``null`` を送ると未割当へ戻す。"""

    entry_ids: list[int] = Field(min_length=1, max_length=500)
    task_id: int | None


class TimeEntryFromOccurrenceRequest(BaseModel):
    """予定の回をそのまま打刻にする。回は ``event_id`` と ``start``（回の始まり。
    ``/api/calendar/occurrences`` の ``start``）で指す。``task_id`` を送らなければ回のタスク。
    """

    event_id: int
    start: AwareDatetime
    task_id: int | None = None


class AutoTimeEntryRequestItem(BaseModel):
    """PC の自動記録の 1 区間。時刻はオフセット付き。``task_id`` は必須（未分類は送らない）。

    ``mode`` は ``fill``（既定。空いている部分だけ）か ``override``（例外作業。手の打刻を切り抜く）。
    ほかの値は 422 ではなく、その区間だけ ``invalid``（ADR-0045）。
    """

    client_ref: str = Field(min_length=1, max_length=64, description="送り手が付けた ID（UUID）")
    started_at: AwareDatetime
    ended_at: AwareDatetime
    task_id: int
    mode: str = Field(default="fill", max_length=32)


class AutoTimeEntriesRequest(BaseModel):
    """PC の自動記録（WinTrack）がまとめて送る区間（1 回に 1〜200 件。ADR-0042・ADR-0045）。

    表題やアプリ名は受け取らない。
    """

    entries: list[AutoTimeEntryRequestItem] = Field(min_length=1, max_length=200)


class AutoTimeEntryResult(BaseModel):
    """1 区間の結果。``entries`` は作った（送り直しなら、そのとき作った）打刻で、作らなかったときは ``[]``。

    - ``created``: 作った（``source = "auto"``。``fill`` は空きの数だけ）
    - ``covered``: ``fill`` で、全部ほかの打刻に覆われていて作らなかった（エラーではない）
    - ``extended``: 同じ ``client_ref`` で、始まりとタスクと ``mode`` が同じまま終わりだけ遅くなった。増えた分だけ
      打刻を伸ばした（伸ばせなければ足した。``fill`` で増えた分が全部覆われていれば何もしない）。ADR-0050
    - ``duplicate``: 同じ ``client_ref`` を既に受け取った（送り直し。終わりを遅くする以外の違いは上書きしない）
    - ``overlap``: ``override`` が、ほかの自動の打刻と重なる
    - ``closed``: 確定済みの締めの期間に掛かる
    - ``invalid``: 時刻の逆転・7 日より前・未来（60 秒の遊びは Start と同じ）・自分のでないタスク・知らない ``mode``
    """

    client_ref: str
    status: Literal["created", "covered", "extended", "duplicate", "overlap", "closed", "invalid"]
    entries: list[TimeEntryResponse]
    error: str | None

    @classmethod
    def from_outcome(cls, outcome: AutoTimeEntryOutcome) -> AutoTimeEntryResult:
        return cls(
            client_ref=outcome.client_ref,
            status=outcome.status.value,
            entries=[TimeEntryResponse.from_view(v) for v in outcome.views],
            error=outcome.error,
        )


class AutoTimeEntriesResponse(BaseModel):
    """送った順に 1 区間ずつの結果。1 件を断っても全体は 200。"""

    results: list[AutoTimeEntryResult]
