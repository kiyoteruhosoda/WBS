"""打刻（task #154 / ADR-0008）。

普段は ``POST /start`` と ``POST /stop`` だけ。画面の上部は ``GET /current`` を見る。
この 3 つだけは打刻アプリ（task #167）からも叩ける ——assay のアクセストークンを
``Authorization: Bearer`` で受け取る（``AppOrWebUserDep``、ADR-0018）。
期間の一覧・1 件の修正・削除と、補正（手で足す・分割・結合・まとめてタスクを振る・
予定の回から作る）は締めの画面（#161 / ADR-0012）のため。
確定済みの締めの期間に掛かる打刻は書き換えられない（409）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from src.application.dto.time_entry_dto import (
    CreateTimeEntryCommand,
    EntryFromOccurrenceCommand,
    MergeTimeEntriesCommand,
    StartTimerCommand,
    UpdateTimeEntryCommand,
)
from src.application.dto.unset import UNSET
from src.domain.exceptions import ValidationError
from src.presentation.api.dependencies import (
    AppOrWebUserDep,
    CurrentUserDep,
    TimeEntryUseCasesDep,
)
from src.presentation.api.schemas.time_entry_schemas import (
    CurrentTimeEntryResponse,
    StartTimeEntryRequest,
    StartTimeEntryResponse,
    StopTimeEntryRequest,
    StopTimeEntryResponse,
    TimeEntryAssignRequest,
    TimeEntryCreateRequest,
    TimeEntryFromOccurrenceRequest,
    TimeEntryMergeRequest,
    TimeEntryResponse,
    TimeEntrySplitRequest,
    TimeEntrySplitResponse,
    TimeEntryUpdateRequest,
)
from src.shared.clock import to_naive_utc, utcnow

router = APIRouter(prefix="/time-entries", tags=["time-entries"])


@router.get("/current", response_model=CurrentTimeEntryResponse)
def get_current_time_entry(
    uc: TimeEntryUseCasesDep, current_user: AppOrWebUserDep
) -> CurrentTimeEntryResponse:
    view = uc.current(current_user.user_id)
    return CurrentTimeEntryResponse(
        entry=TimeEntryResponse.from_view(view) if view is not None else None,
        server_now=utcnow(),
    )


@router.post("/start", response_model=StartTimeEntryResponse, status_code=status.HTTP_201_CREATED)
def start_time_entry(
    uc: TimeEntryUseCasesDep,
    current_user: AppOrWebUserDep,
    body: StartTimeEntryRequest | None = None,
) -> StartTimeEntryResponse:
    body = body or StartTimeEntryRequest()
    command = StartTimerCommand(
        user_id=current_user.user_id,
        # 送らなければ既定の順で決める。null は「未割当で始める」
        task_id=body.task_id if "task_id" in body.model_fields_set else UNSET,
        memo=body.memo,
        at=to_naive_utc(body.at) if body.at is not None else None,
    )
    result = uc.start(command)
    return StartTimeEntryResponse(
        started=TimeEntryResponse.from_view(result.started),
        stopped=TimeEntryResponse.from_view(result.stopped) if result.stopped else None,
        server_now=utcnow(),
    )


@router.post("/stop", response_model=StopTimeEntryResponse)
def stop_time_entry(
    uc: TimeEntryUseCasesDep,
    current_user: AppOrWebUserDep,
    body: StopTimeEntryRequest | None = None,
) -> StopTimeEntryResponse:
    at = body.at if body is not None else None
    view = uc.stop(current_user.user_id, to_naive_utc(at) if at is not None else None)
    return StopTimeEntryResponse(
        stopped=TimeEntryResponse.from_view(view) if view is not None else None,
        server_now=utcnow(),
    )


@router.get("", response_model=list[TimeEntryResponse])
def list_time_entries(
    uc: TimeEntryUseCasesDep,
    current_user: CurrentUserDep,
    start: Annotated[AwareDatetime, Query(description="区間の始まり（含む）。オフセット付き")],
    end: Annotated[AwareDatetime, Query(description="区間の終わり（含まない）。オフセット付き")],
) -> list[TimeEntryResponse]:
    """``[start, end)`` に掛かる打刻を始まりの順に。日をまたぐ打刻は両方の日に出る。"""
    views = uc.list_in_period(current_user.user_id, to_naive_utc(start), to_naive_utc(end))
    return [TimeEntryResponse.from_view(v) for v in views]


@router.post("", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    body: TimeEntryCreateRequest, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> TimeEntryResponse:
    """空き時間に打刻を足す（``source=manual``）。止まった打刻だけを作れる。"""
    command = CreateTimeEntryCommand(
        user_id=current_user.user_id,
        started_at=to_naive_utc(body.started_at),
        ended_at=to_naive_utc(body.ended_at),
        task_id=body.task_id,
        memo=body.memo,
    )
    return TimeEntryResponse.from_view(uc.create(command))


@router.post("/merge", response_model=TimeEntryResponse)
def merge_time_entries(
    body: TimeEntryMergeRequest, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> TimeEntryResponse:
    """つなぐ。いちばん早い打刻が残り、始まりから最後の終わりまでの 1 本になる（ほかは消える）。"""
    command = MergeTimeEntriesCommand(
        user_id=current_user.user_id,
        entry_ids=body.entry_ids,
        task_id=body.task_id if "task_id" in body.model_fields_set else UNSET,
    )
    return TimeEntryResponse.from_view(uc.merge(command))


@router.post("/assign", response_model=list[TimeEntryResponse])
def assign_task_to_time_entries(
    body: TimeEntryAssignRequest, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> list[TimeEntryResponse]:
    """まとめてタスクを振る（``null`` で未割当へ戻す）。"""
    views = uc.assign_task(current_user.user_id, body.entry_ids, body.task_id)
    return [TimeEntryResponse.from_view(v) for v in views]


@router.post(
    "/from-occurrence", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED
)
def create_time_entry_from_occurrence(
    body: TimeEntryFromOccurrenceRequest, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> TimeEntryResponse:
    """予定の回をそのまま打刻にする（``source=schedule``）。終日の回・まだ終わっていない回は 422。"""
    command = EntryFromOccurrenceCommand(
        user_id=current_user.user_id,
        event_id=body.event_id,
        start=to_naive_utc(body.start),
        task_id=body.task_id if "task_id" in body.model_fields_set else UNSET,
    )
    return TimeEntryResponse.from_view(uc.create_from_occurrence(command))


@router.post("/{entry_id}/split", response_model=TimeEntrySplitResponse)
def split_time_entry(
    entry_id: int,
    body: TimeEntrySplitRequest,
    uc: TimeEntryUseCasesDep,
    current_user: CurrentUserDep,
) -> TimeEntrySplitResponse:
    """``at`` で 2 本に分ける。元の打刻は ``at`` で終わり、続きは新しい打刻（``source=split``）。"""
    result = uc.split(entry_id, current_user.user_id, to_naive_utc(body.at))
    return TimeEntrySplitResponse(
        first=TimeEntryResponse.from_view(result.first),
        second=TimeEntryResponse.from_view(result.second),
    )


@router.get("/{entry_id}", response_model=TimeEntryResponse)
def get_time_entry(
    entry_id: int, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> TimeEntryResponse:
    return TimeEntryResponse.from_view(uc.get(entry_id, current_user.user_id))


@router.patch("/{entry_id}", response_model=TimeEntryResponse)
def update_time_entry(
    entry_id: int,
    body: TimeEntryUpdateRequest,
    uc: TimeEntryUseCasesDep,
    current_user: CurrentUserDep,
) -> TimeEntryResponse:
    sent = body.model_fields_set
    if "started_at" in sent and body.started_at is None:
        raise ValidationError("started_at cannot be null")
    if "ended_at" in sent and body.ended_at is None:
        raise ValidationError("ended_at cannot be null (a stopped entry cannot run again)")
    command = UpdateTimeEntryCommand(
        started_at=to_naive_utc(body.started_at) if body.started_at is not None else UNSET,
        ended_at=to_naive_utc(body.ended_at) if body.ended_at is not None else UNSET,
        task_id=body.task_id if "task_id" in sent else UNSET,
        memo=body.memo if "memo" in sent else UNSET,
    )
    return TimeEntryResponse.from_view(uc.update(entry_id, current_user.user_id, command))


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    entry_id: int, uc: TimeEntryUseCasesDep, current_user: CurrentUserDep
) -> None:
    uc.delete(entry_id, current_user.user_id)
