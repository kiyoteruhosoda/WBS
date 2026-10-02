"""予定のドメイン試験の組み立て（移植元 CoreTests の ``Utc(...)`` や ``Rec`` に当たる）。"""

from __future__ import annotations

from datetime import date, datetime, time

from src.domain.entities.calendar import Calendar, DayOffReason
from src.domain.entities.calendar_event import (
    CalendarEvent,
    EventException,
    EventKind,
    EventMove,
)
from src.domain.entities.day_off import DayOff
from src.domain.services.day_off_layers import DayOffLayers
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import RecurringEventSchedule, SingleEventSchedule
from src.domain.value_objects.local_schedule_point import start_instant
from src.domain.value_objects.recurrence import (
    WEEKDAYS_MON_TO_FRI,
    AdjustmentRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
)
from src.domain.value_objects.time_zone import TimeZoneId

TOKYO = TimeZoneId("Asia/Tokyo")
NEW_YORK = TimeZoneId("America/New_York")
UTC_ZONE = TimeZoneId("UTC")
NOW = datetime(2026, 5, 1, 0, 0)


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0, tz: TimeZoneId = TOKYO) -> datetime:
    """``tz`` の壁時計を UTC の瞬間（naive）にする。"""
    return start_instant(date(y, mo, d), time(h, mi), tz.zone)


def weekly_rule(
    *weekdays: Weekday,
    end: date = date(2026, 12, 31),
    interval: int = 1,
    adjustment: AdjustmentRule | None = None,
) -> RecurrenceRule:
    return RecurrenceRule(
        RecurrenceType.WEEKLY, interval, end,
        weekly=WeeklyRule(tuple(weekdays) or (Weekday.MONDAY,)), adjustment=adjustment,
    )


def single_event(
    start_utc: datetime,
    duration_minutes: int = 60,
    *,
    event_id: int | None = 1,
    user_id: int = 1,
    title: str = "単発",
    location: str | None = None,
    tz: TimeZoneId = TOKYO,
    color_key: EventColorKey = EventColorKey.DEFAULT,
) -> CalendarEvent:
    event = CalendarEvent.create_single(
        user_id=user_id, title=title, time_zone=tz,
        schedule=SingleEventSchedule(start_utc, duration_minutes), created_at=NOW,
        location=location, color_key=color_key,
    )
    event.id = event_id
    return event


def recurring_event(
    anchor_utc: datetime,
    rule: RecurrenceRule,
    duration_minutes: int = 60,
    *,
    event_id: int | None = 1,
    user_id: int = 1,
    title: str = "定例会議",
    location: str | None = None,
    tz: TimeZoneId = TOKYO,
    exceptions: list[EventException] | None = None,
    moves: list[EventMove] | None = None,
) -> CalendarEvent:
    """保存済みの形で組み立てる（移植元の ``Reconstitute`` に当たる）。"""
    return CalendarEvent(
        id=event_id, user_id=user_id, kind=EventKind.RECURRING,
        title=title, time_zone=tz,
        recurring_schedule=RecurringEventSchedule(anchor_utc, duration_minutes, rule),
        location=location,
        exceptions=list(exceptions or []), moves=list(moves or []),
        created_at=NOW, updated_at=NOW,
    )


def weekly_monday_from_0420(**kwargs) -> CalendarEvent:
    """移植元 ``CreateWeeklyMonday``: 2026-04-20 から毎週月曜 10:00〜11:00、会議室A。"""
    kwargs.setdefault("title", "週次会議")
    kwargs.setdefault("location", "会議室A")
    return recurring_event(utc(2026, 4, 20, 10, 0), weekly_rule(Weekday.MONDAY), 60, **kwargs)


NATIONAL_LAYER_ID = 13


def weekday_layers(
    *holidays: date,
    user_id: int = 1,
    workdays: frozenset[Weekday] = WEEKDAYS_MON_TO_FRI,
) -> DayOffLayers:
    """月〜金が営業日で、``holidays`` が「日本の祝日」の層（休みとして数える）の日の休みの層。"""
    national = Calendar.create_layer(user_id, DayOffReason.NATIONAL_HOLIDAY, NOW)
    national.id = NATIONAL_LAYER_ID
    return DayOffLayers(
        workdays=workdays,
        layers=[national],
        days_off=[DayOff(NATIONAL_LAYER_ID, d, "祝") for d in holidays],
    )
