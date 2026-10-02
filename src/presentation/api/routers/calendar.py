"""予定の API（task #156、ADR-0009）。

- 回を期間で引く（閲覧者のタイムゾーンへ投影済み）: ``GET /calendar/occurrences``
- この先の通知を引く（打刻アプリが Bearer でも叩く。ADR-0021）: ``GET /calendar/alarms``
- 祝日を期間で引く（有効な営業日カレンダーから）: ``GET /calendar/holidays``
- 予定の CRUD: ``/calendar/events``
- 繰り返しの編集: すべて（``PUT .../series``）・この回以降（``POST .../occurrences/following``）・
  この回だけ（``POST .../occurrences/split``）
- 回の操作: 飛ばす・戻す・移動・移動の取り消し・以降を消す（``POST .../occurrences/<操作>``）
- タスクの分類の回の済み（ADR-0025）: ``PUT .../done``

他人の予定は 404。``expected_version`` が今の版と違えば 409。
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.application.dto.calendar_event_dto import (
    ChangeFollowingOccurrencesCommand,
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    MoveOccurrenceCommand,
    OccurrenceCommand,
    OccurrenceDoneCommand,
    SplitThisOccurrenceCommand,
    UpdateEventCommand,
    UpdateRecurringSeriesCommand,
)
from src.application.dto.unset import UNSET, UnsetType
from src.domain.value_objects.event_alarm import EventAlarm
from src.presentation.api.dependencies import (
    AppOrWebUserDep,
    BusinessCalendarUseCasesDep,
    CalendarEventUseCasesDep,
    CurrentUserDep,
)
from src.presentation.api.schemas.calendar_schemas import (
    CalendarAlarmResponse,
    CalendarAlarmsResponse,
    CalendarEventCreateRequest,
    CalendarEventResponse,
    CalendarEventUpdateRequest,
    CalendarOccurrenceResponse,
    EventAlarmSchema,
    FollowingOccurrencesChangeRequest,
    HolidaySchema,
    OccurrenceActionRequest,
    OccurrenceDoneRequest,
    OccurrenceDoneResponse,
    OccurrenceKeyResponse,
    OccurrenceMoveRequest,
    SeriesUpdateRequest,
    ThisOccurrenceChangeRequest,
)
from src.shared.clock import to_naive_utc

router = APIRouter(prefix="/calendar", tags=["calendar"])


FromDate = Annotated[dt.date, Query(alias="from", description="期間の初日（ローカル日、含む）")]
ToDate = Annotated[dt.date, Query(alias="to", description="期間の末日（ローカル日、含む）")]


def _alarm_input(
    alarm: EventAlarmSchema | None, fields_set: set[str]
) -> EventAlarm | None | UnsetType:
    """本文の ``alarm``。省かれたら ``UNSET``（作る: 既定・直す: 今のまま）、``null`` は通知なし。"""
    if "alarm" not in fields_set:
        return UNSET
    return alarm.to_alarm() if alarm is not None else None


# ── 引く ────────────────────────────────────────────────────────────────────


@router.get("/occurrences", response_model=list[CalendarOccurrenceResponse])
def list_occurrences(
    from_date: FromDate,
    to_date: ToDate,
    current_user: CurrentUserDep,
    events: CalendarEventUseCasesDep,
    time_zone: Annotated[
        str | None, Query(description="閲覧者のタイムゾーン（IANA 名）。省くと利用者の設定")
    ] = None,
) -> list[CalendarOccurrenceResponse]:
    views = events.list_occurrence_views(
        current_user.user_id, from_date, to_date, time_zone or current_user.timezone
    )
    return [CalendarOccurrenceResponse.from_view(v) for v in views]


@router.get("/alarms", response_model=CalendarAlarmsResponse)
def list_alarms(
    window_start: Annotated[
        dt.datetime,
        Query(
            alias="from",
            description="期間の始まり（UTC 瞬間、含む）。`Z` 付き ISO 8601。オフセットの無い値は UTC",
        ),
    ],
    window_end: Annotated[
        dt.datetime,
        Query(alias="to", description="期間の終わり（UTC 瞬間、含まない）。from から 7 日まで"),
    ],
    current_user: AppOrWebUserDep,
    events: CalendarEventUseCasesDep,
) -> CalendarAlarmsResponse:
    """``[from, to)`` に知らせる時刻が来る通知を、知らせる時刻の順に返す（ADR-0021）。

    打刻アプリが端末で通知を出すための口。⚠ Cookie のほか assay のアクセストークン
    （``Authorization: Bearer``、ADR-0018）でも読める。読むだけ。
    """
    planned = events.list_planned_alarms(current_user.user_id, window_start, window_end)
    return CalendarAlarmsResponse(
        window_start=to_naive_utc(window_start),
        window_end=to_naive_utc(window_end),
        alarms=[CalendarAlarmResponse.from_planned(p) for p in planned],
    )


@router.get("/holidays", response_model=list[HolidaySchema])
def list_holidays(
    from_date: FromDate, to_date: ToDate, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> list[HolidaySchema]:
    return [
        HolidaySchema.from_holiday(h)
        for h in calendars.list_holidays(current_user.user_id, from_date, to_date)
    ]


@router.get("/events", response_model=list[CalendarEventResponse])
def list_events(
    from_date: FromDate, to_date: ToDate, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> list[CalendarEventResponse]:
    """期間に回がありうる予定（粗い絞り込み。回そのものは ``/calendar/occurrences``）。"""
    found = events.find_by_period(current_user.user_id, from_date, to_date)
    return [CalendarEventResponse.from_event(e) for e in found]


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
def get_event(event_id: int, current_user: CurrentUserDep, events: CalendarEventUseCasesDep) -> CalendarEventResponse:
    return CalendarEventResponse.from_event(events.get_event(event_id, current_user.user_id))


# ── 作る・直す・消す ────────────────────────────────────────────────────────


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    body: CalendarEventCreateRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    time_zone = body.time_zone or current_user.timezone
    if body.recurrence is None:
        created = events.create_single_event(
            CreateSingleEventCommand(
                user_id=current_user.user_id,
                title=body.title,
                time_zone=time_zone,
                start_utc=body.start,
                duration_minutes=body.duration_minutes,
                location=body.location,
                description=body.description,
                color_key=body.color_key,
                task_id=body.task_id,
                alarm=_alarm_input(body.alarm, body.model_fields_set),
                event_type=body.event_type,
                calendar_id=body.calendar_id,
            )
        )
    else:
        created = events.create_recurring_event(
            CreateRecurringEventCommand(
                user_id=current_user.user_id,
                title=body.title,
                time_zone=time_zone,
                anchor_utc=body.start,
                duration_minutes=body.duration_minutes,
                recurrence_rule=body.recurrence.to_rule(),
                location=body.location,
                description=body.description,
                color_key=body.color_key,
                task_id=body.task_id,
                alarm=_alarm_input(body.alarm, body.model_fields_set),
                event_type=body.event_type,
                calendar_id=body.calendar_id,
            )
        )
    return CalendarEventResponse.from_event(created)


@router.put("/events/{event_id}", response_model=CalendarEventResponse)
def update_event(
    event_id: int, body: CalendarEventUpdateRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """詳細を置き換える。単発なら ``start`` と ``duration_minutes`` で日時も移す。"""
    updated = events.update_event(
        UpdateEventCommand(
            event_id=event_id,
            user_id=current_user.user_id,
            title=body.title,
            location=body.location,
            description=body.description,
            task_id=body.task_id,
            start_utc=body.start,
            duration_minutes=body.duration_minutes,
            color_key=body.color_key,
            alarm=_alarm_input(body.alarm, body.model_fields_set),
            event_type=body.event_type,
            calendar_id=body.calendar_id,
            expected_version=body.expected_version,
        )
    )
    return CalendarEventResponse.from_event(updated)


@router.put("/events/{event_id}/series", response_model=CalendarEventResponse)
def update_series(
    event_id: int, body: SeriesUpdateRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """繰り返しの「すべて」を直す。"""
    updated = events.update_recurring_series(
        UpdateRecurringSeriesCommand(
            event_id=event_id,
            user_id=current_user.user_id,
            title=body.title,
            duration_minutes=body.duration_minutes,
            recurrence_rule=body.recurrence.to_rule(),
            location=body.location,
            description=body.description,
            task_id=body.task_id,
            color_key=body.color_key,
            anchor_utc=body.start,
            alarm=_alarm_input(body.alarm, body.model_fields_set),
            event_type=body.event_type,
            calendar_id=body.calendar_id,
            expected_version=body.expected_version,
        )
    )
    return CalendarEventResponse.from_event(updated)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    current_user: CurrentUserDep,
    events: CalendarEventUseCasesDep,
    expected_version: int | None = None,
) -> None:
    events.delete_event(event_id, current_user.user_id, expected_version)


# ── 繰り返しの回 ────────────────────────────────────────────────────────────


@router.post(
    "/events/{event_id}/occurrences/following",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def change_following_occurrences(
    event_id: int,
    body: FollowingOccurrencesChangeRequest,
    current_user: CurrentUserDep,
    events: CalendarEventUseCasesDep,
) -> CalendarEventResponse:
    """「この回以降」を直す。新しい系列を返す（先頭の回からなら元の系列は消える）。"""
    created = events.change_following_occurrences(
        ChangeFollowingOccurrencesCommand(
            event_id=event_id,
            user_id=current_user.user_id,
            from_occurrence_key=body.occurrence.to_key(),
            title=body.title,
            anchor_utc=body.start,
            duration_minutes=body.duration_minutes,
            recurrence_rule=body.recurrence.to_rule(),
            location=body.location,
            description=body.description,
            color_key=body.color_key,
            task_id=body.task_id if "task_id" in body.model_fields_set else UNSET,
            alarm=_alarm_input(body.alarm, body.model_fields_set),
            event_type=body.event_type,
            calendar_id=body.calendar_id,
            expected_version=body.expected_version,
        )
    )
    return CalendarEventResponse.from_event(created)


@router.post(
    "/events/{event_id}/occurrences/split",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def split_this_occurrence(
    event_id: int,
    body: ThisOccurrenceChangeRequest,
    current_user: CurrentUserDep,
    events: CalendarEventUseCasesDep,
) -> CalendarEventResponse:
    """「この回だけ」を直す。系列からその回を飛ばし、新しい単発を返す。"""
    created = events.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event_id=event_id,
            user_id=current_user.user_id,
            occurrence_key=body.occurrence.to_key(),
            title=body.title,
            start_utc=body.start,
            duration_minutes=body.duration_minutes,
            location=body.location,
            description=body.description,
            color_key=body.color_key,
            task_id=body.task_id if "task_id" in body.model_fields_set else UNSET,
            alarm=_alarm_input(body.alarm, body.model_fields_set),
            event_type=body.event_type,
            calendar_id=body.calendar_id,
            expected_version=body.expected_version,
        )
    )
    return CalendarEventResponse.from_event(created)


def _occurrence_command(
    event_id: int, body: OccurrenceActionRequest, user_id: int
) -> OccurrenceCommand:
    return OccurrenceCommand(
        event_id=event_id,
        user_id=user_id,
        occurrence_key=body.occurrence.to_key(),
        expected_version=body.expected_version,
    )


@router.post("/events/{event_id}/occurrences/skip", response_model=CalendarEventResponse)
def skip_occurrence(
    event_id: int, body: OccurrenceActionRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """その回を飛ばす（「この回を削除」）。"""
    updated = events.skip_occurrence(_occurrence_command(event_id, body, current_user.user_id))
    return CalendarEventResponse.from_event(updated)


@router.post("/events/{event_id}/occurrences/restore", response_model=CalendarEventResponse)
def restore_occurrence(
    event_id: int, body: OccurrenceActionRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """飛ばした回を戻す。"""
    updated = events.restore_occurrence(_occurrence_command(event_id, body, current_user.user_id))
    return CalendarEventResponse.from_event(updated)


@router.post("/events/{event_id}/occurrences/move", response_model=CalendarEventResponse)
def move_occurrence(
    event_id: int, body: OccurrenceMoveRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """その回だけ別の日時へ移す。"""
    updated = events.move_occurrence(
        MoveOccurrenceCommand(
            event_id=event_id,
            user_id=current_user.user_id,
            occurrence_key=body.occurrence.to_key(),
            start_utc=body.start,
            duration_minutes=body.duration_minutes,
            title=body.title,
            location=body.location,
            expected_version=body.expected_version,
        )
    )
    return CalendarEventResponse.from_event(updated)


@router.post("/events/{event_id}/occurrences/cancel-move", response_model=CalendarEventResponse)
def cancel_move_occurrence(
    event_id: int, body: OccurrenceActionRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> CalendarEventResponse:
    """移した回を系列どおりの位置へ戻す。"""
    updated = events.cancel_move_occurrence(
        _occurrence_command(event_id, body, current_user.user_id)
    )
    return CalendarEventResponse.from_event(updated)


@router.put("/events/{event_id}/done", response_model=OccurrenceDoneResponse)
def set_occurrence_done(
    event_id: int, body: OccurrenceDoneRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> OccurrenceDoneResponse:
    """タスクの分類の予定の回に済みを付ける・外す（ADR-0025）。

    単発は ``occurrence`` を null、繰り返しは回の ``series_key`` を渡す（移した回も元の鍵）。
    予定の分類が「予定」なら 422、系列に無い回（飛ばした回など）は 404。予定の版は進まない。
    """
    key = body.occurrence.to_key() if body.occurrence is not None else None
    done = events.set_occurrence_done(
        OccurrenceDoneCommand(
            event_id=event_id, user_id=current_user.user_id, occurrence_key=key, done=body.done
        )
    )
    return OccurrenceDoneResponse(
        event_id=event_id,
        occurrence=OccurrenceKeyResponse.from_key(key) if key is not None else None,
        done=done,
    )


@router.post(
    "/events/{event_id}/occurrences/delete-following", status_code=status.HTTP_204_NO_CONTENT
)
def delete_following_occurrences(
    event_id: int, body: OccurrenceActionRequest, current_user: CurrentUserDep, events: CalendarEventUseCasesDep
) -> None:
    """この回以降を消す（先頭の回なら系列ごと）。"""
    events.delete_following_occurrences(
        _occurrence_command(event_id, body, current_user.user_id)
    )
