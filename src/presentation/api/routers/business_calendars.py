"""営業日カレンダーと祝日の API（task #156、ADR-0009）。

祝日の入れ方は 3 つ: 1 日ずつ（``POST .../holidays``）・まとめて（``POST .../holidays/bulk``）・
日本の祝日を年ごとに（``POST .../holidays/japan``。暦から出し、外へは取りに行かない）。
他人のカレンダーは 404。
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, status

from src.application.dto.business_calendar_dto import (
    CreateBusinessCalendarCommand,
    UpdateBusinessCalendarCommand,
)
from src.presentation.api.dependencies import BusinessCalendarUseCasesDep, CurrentUserDep
from src.presentation.api.schemas.calendar_schemas import (
    BusinessCalendarCreateRequest,
    BusinessCalendarResponse,
    BusinessCalendarUpdateRequest,
    HolidaysBulkRequest,
    HolidaySchema,
    JapaneseHolidaysImportRequest,
)

router = APIRouter(prefix="/business-calendars", tags=["business-calendars"])


@router.get("", response_model=list[BusinessCalendarResponse])
def list_calendars(
    current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> list[BusinessCalendarResponse]:
    return [
        BusinessCalendarResponse.from_calendar(c)
        for c in calendars.list_calendars(current_user.user_id)
    ]


@router.post("", response_model=BusinessCalendarResponse, status_code=status.HTTP_201_CREATED)
def create_calendar(
    body: BusinessCalendarCreateRequest, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> BusinessCalendarResponse:
    created = calendars.create_calendar(
        CreateBusinessCalendarCommand(
            user_id=current_user.user_id,
            name=body.name,
            time_zone=body.time_zone or current_user.timezone,
            workdays=frozenset(body.workdays),
            shift_on_holidays_only=body.shift_on_holidays_only,
            is_enabled=body.is_enabled,
        )
    )
    return BusinessCalendarResponse.from_calendar(created)


@router.get("/{calendar_id}", response_model=BusinessCalendarResponse)
def get_calendar(
    calendar_id: int, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> BusinessCalendarResponse:
    return BusinessCalendarResponse.from_calendar(
        calendars.get_calendar(calendar_id, current_user.user_id)
    )


@router.put("/{calendar_id}", response_model=BusinessCalendarResponse)
def update_calendar(
    calendar_id: int,
    body: BusinessCalendarUpdateRequest,
    current_user: CurrentUserDep,
    calendars: BusinessCalendarUseCasesDep,
) -> BusinessCalendarResponse:
    updated = calendars.update_calendar(
        UpdateBusinessCalendarCommand(
            calendar_id=calendar_id,
            user_id=current_user.user_id,
            name=body.name,
            workdays=frozenset(body.workdays),
            shift_on_holidays_only=body.shift_on_holidays_only,
            is_enabled=body.is_enabled,
        )
    )
    return BusinessCalendarResponse.from_calendar(updated)


@router.delete("/{calendar_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar(calendar_id: int, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep) -> None:
    """消す。参照していた繰り返しは、以後シフトせずに名目の日に出る。"""
    calendars.delete_calendar(calendar_id, current_user.user_id)


@router.post("/{calendar_id}/holidays", response_model=BusinessCalendarResponse)
def add_holiday(
    calendar_id: int, body: HolidaySchema, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> BusinessCalendarResponse:
    """祝日を 1 日足す。同じ日がすでにあれば何もしない。"""
    updated = calendars.add_holiday(calendar_id, current_user.user_id, body.date, body.name)
    return BusinessCalendarResponse.from_calendar(updated)


@router.post("/{calendar_id}/holidays/bulk", response_model=BusinessCalendarResponse)
def add_holidays(
    calendar_id: int,
    body: HolidaysBulkRequest,
    current_user: CurrentUserDep,
    calendars: BusinessCalendarUseCasesDep,
) -> BusinessCalendarResponse:
    """祝日をまとめて足す（年ごとの一括登録）。すでにある日はそのまま。"""
    updated = calendars.add_holidays(
        calendar_id, current_user.user_id, [h.to_holiday() for h in body.holidays]
    )
    return BusinessCalendarResponse.from_calendar(updated)


@router.post("/{calendar_id}/holidays/japan", response_model=BusinessCalendarResponse)
def import_japanese_holidays(
    calendar_id: int,
    body: JapaneseHolidaysImportRequest,
    current_user: CurrentUserDep,
    calendars: BusinessCalendarUseCasesDep,
) -> BusinessCalendarResponse:
    """その年の日本の祝日・振替休日・国民の休日を足す（2007〜2099 年）。"""
    updated = calendars.import_japanese_national_holidays(
        calendar_id, current_user.user_id, body.year
    )
    return BusinessCalendarResponse.from_calendar(updated)


@router.delete("/{calendar_id}/holidays/{holiday_date}", response_model=BusinessCalendarResponse)
def remove_holiday(
    calendar_id: int, holiday_date: dt.date, current_user: CurrentUserDep, calendars: BusinessCalendarUseCasesDep
) -> BusinessCalendarResponse:
    updated = calendars.remove_holiday(calendar_id, current_user.user_id, holiday_date)
    return BusinessCalendarResponse.from_calendar(updated)
