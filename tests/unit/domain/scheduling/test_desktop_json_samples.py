"""デスクトップ版の JSON の入力例（移植元 NolumiaSchedulerTest/Inputs/Json/*.json）。

入力例は旧形式（``start``/``end``・``startDate``/``startTime``/``endTime``・``allDay``）なので、
移植元 docs/time-model.md §9 の変換規則で今のドメインへ組み立ててから展開する。
入力例には期待値が付いていないので、期待値は暦から手で出した（曜日は試験の中で確かめる）。
公開/非公開（``visibility``）と予定種別（``eventType``）は持ってこない範囲なので読み捨てる。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pytest

from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.entities.calendar_event import (
    CalendarEvent,
    EventException,
    EventKind,
    EventMove,
    ExceptionOverride,
)
from src.domain.services.occurrence_expander import OccurrenceExpander
from src.domain.value_objects.event_schedule import (
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.local_schedule_point import (
    MINUTES_PER_DAY,
    start_instant,
    to_naive_utc,
    wrapping_duration_minutes,
)
from src.domain.value_objects.recurrence import (
    AdjustmentCondition,
    AdjustmentRule,
    AdjustmentShiftUnit,
    DayOfMonthMonthlyRule,
    DayOfMonthYearlyRule,
    LastDayOfMonthMonthlyRule,
    MonthlyRule,
    NthWeekdayMonthlyRule,
    NthWeekdayYearlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
    YearlyRule,
)
from src.domain.value_objects.time_zone import TimeZoneId

SAMPLES = Path(__file__).resolve().parents[3] / "fixtures" / "nolumia_scheduler"
CALENDAR_IDS = {"jp_default": 1}
"""移植元のカレンダー ID（文字列）を、こちらの採番（整数）へ読み替える。"""

expander = OccurrenceExpander()


# ── 旧形式 → ドメイン（time-model §9）──────────────────────────────────────


def _load(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def _time(text: str | None) -> time | None:
    return time.fromisoformat(text) if text else None


def _key(occurrence_local: str) -> OccurrenceKey:
    local = datetime.fromisoformat(occurrence_local)
    return OccurrenceKey(local.date(), local.time())


def _monthly(raw: dict[str, Any]) -> MonthlyRule:
    if raw["mode"] == "NTH_WEEKDAY":
        return NthWeekdayMonthlyRule(raw["weekIndex"], Weekday(raw["weekday"]))
    if raw["mode"] == "LAST_DAY":
        return LastDayOfMonthMonthlyRule()
    return DayOfMonthMonthlyRule(raw["day"])


def _yearly(raw: dict[str, Any]) -> YearlyRule:
    if raw["mode"] == "NTH_WEEKDAY":
        return NthWeekdayYearlyRule(raw["month"], raw["weekIndex"], Weekday(raw["weekday"]))
    return DayOfMonthYearlyRule(raw["month"], raw["day"])


def _rule(raw: dict[str, Any]) -> RecurrenceRule:
    adjustment = None
    if raw.get("adjustment"):
        a = raw["adjustment"]
        adjustment = AdjustmentRule(
            AdjustmentCondition(a["condition"]), AdjustmentShiftUnit(a["shiftUnit"]),
            a["shiftAmount"], CALENDAR_IDS.get(a.get("calendarId") or ""),
        )
    return RecurrenceRule(
        RecurrenceType(raw["ruleType"]), raw["interval"], date.fromisoformat(raw["endDate"]),
        weekly=WeeklyRule(tuple(Weekday(w) for w in raw["weekly"]["weekdays"])) if raw.get("weekly") else None,
        monthly=_monthly(raw["monthly"]) if raw.get("monthly") else None,
        yearly=_yearly(raw["yearly"]) if raw.get("yearly") else None,
        adjustment=adjustment,
    )


def _exception(raw: dict[str, Any]) -> EventException:
    key = _key(raw["occurrenceLocal"])
    if raw["action"] == "SKIP":
        return EventException.skip(key)
    ov = raw["override"]
    start, end = _time(ov.get("startTime")), _time(ov.get("endTime"))
    return EventException.override_with(
        key,
        ExceptionOverride(
            title=ov.get("title"), location=ov.get("location"), start_time=start,
            duration_minutes=wrapping_duration_minutes(start, end) if start and end else None,
        ),
    )


def _move(raw: dict[str, Any]) -> EventMove:
    start, end = _time(raw.get("newStartTime")), _time(raw.get("newEndTime"))
    return EventMove(
        _key(raw["occurrenceLocal"]), date.fromisoformat(raw["newDate"]), start,
        wrapping_duration_minutes(start, end) if start and end else None,
        raw.get("title"), raw.get("location"),
    )


def desktop_event(name: str, event_id: int = 1, user_id: int = 1) -> CalendarEvent:
    raw = _load(name)
    tz = TimeZoneId(raw["timezone"])
    common: dict[str, Any] = {
        "id": event_id, "user_id": user_id, "title": raw["title"], "time_zone": tz,
        "location": raw.get("location"), "description": raw.get("description"),
        "version": raw["version"],
        "created_at": to_naive_utc(datetime.fromisoformat(raw["createdAt"])),
        "updated_at": to_naive_utc(datetime.fromisoformat(raw["updatedAt"])),
    }
    if raw["kind"] == "Single":
        start = datetime.fromisoformat(raw["start"])
        end = datetime.fromisoformat(raw["end"])
        duration = int((end - start).total_seconds() // 60)
        return CalendarEvent(
            kind=EventKind.SINGLE, single_schedule=SingleEventSchedule(start, duration), **common
        )
    start_date = date.fromisoformat(raw["startDate"])
    if raw["allDay"]:
        start_time, duration = time(0, 0), MINUTES_PER_DAY
    else:
        start_time = _time(raw["startTime"]) or time(0, 0)
        end_time = _time(raw["endTime"]) or time(0, 0)
        duration = wrapping_duration_minutes(start_time, end_time)
    anchor = start_instant(start_date, start_time, tz.zone)
    return CalendarEvent(
        kind=EventKind.RECURRING,
        recurring_schedule=RecurringEventSchedule(anchor, duration, _rule(raw["recurrence"])),
        exceptions=[_exception(e) for e in raw.get("exceptions", [])],
        moves=[_move(m) for m in raw.get("moves", [])],
        **common,
    )


def desktop_calendar(extra_holidays: tuple[Holiday, ...] = ()) -> BusinessCalendar:
    raw = _load("営業日カレンダーサンプル")
    return BusinessCalendar(
        id=CALENDAR_IDS[raw["id"]], user_id=1, name=raw["name"], time_zone=TimeZoneId(raw["timezone"]),
        workdays=frozenset(Weekday(w) for w in raw["workdaysOfWeek"]),
        holidays=[Holiday(date.fromisoformat(h["date"]), h["name"]) for h in raw["holidays"]]
        + list(extra_holidays),
    )


def _dates(event: CalendarEvent, from_date: date, to_date: date, calendar=None) -> list[date]:
    return [o.date for o in expander.expand(event, from_date, to_date, calendar)]


# ── 単発 ────────────────────────────────────────────────────────────────


def test_single_normal() -> None:
    event = desktop_event("単発・通常イベント")
    assert event.single_schedule is not None
    assert event.single_schedule.start_utc == datetime(2026, 4, 21, 5, 0)  # 14:00 JST
    assert event.single_schedule.duration_minutes == 90
    [occurrence] = expander.expand(event, date(2026, 4, 1), date(2026, 4, 30))
    assert (occurrence.date, occurrence.start_time, occurrence.location) == (
        date(2026, 4, 21), time(14, 0), "東京本社",
    )
    assert event.description == "月次定例訪問"


def test_single_crossing_midnight() -> None:
    event = desktop_event("単発・日またぎイベント")
    [occurrence] = expander.expand(event, date(2026, 4, 25), date(2026, 4, 26))
    assert (occurrence.date, occurrence.start_time, occurrence.duration_minutes) == (
        date(2026, 4, 25), time(23, 0), 180,
    )
    assert occurrence.crosses_midnight
    assert event.active_date_span() == (date(2026, 4, 25), date(2026, 4, 26))


def test_single_all_day() -> None:
    event = desktop_event("単発・終日イベント")
    [occurrence] = expander.expand(event, date(2026, 5, 1), date(2026, 5, 1))
    assert occurrence.is_all_day
    assert event.active_date_span() == (date(2026, 5, 1), date(2026, 5, 1))


# ── 繰り返し ────────────────────────────────────────────────────────────


def test_weekly_monday_10_to_11() -> None:
    event = desktop_event("毎週月曜 1000-1100")
    occurrences = expander.expand(event, date(2026, 4, 1), date(2026, 5, 11))
    assert [o.date for o in occurrences] == [
        date(2026, 4, 20), date(2026, 4, 27), date(2026, 5, 4), date(2026, 5, 11)
    ]
    assert all(Weekday.of(o.date) == Weekday.MONDAY for o in occurrences)
    assert all((o.start_time, o.duration_minutes) == (time(10, 0), 60) for o in occurrences)


def test_weekly_all_day_friday_starting_on_a_monday() -> None:
    # 開始日 4/20 は月曜。金曜の規則なので最初の回は 4/24。
    event = desktop_event("繰り返し・終日イベント")
    occurrences = expander.expand(event, date(2026, 4, 20), date(2026, 5, 8))
    assert [o.date for o in occurrences] == [date(2026, 4, 24), date(2026, 5, 1), date(2026, 5, 8)]
    assert all(o.is_all_day for o in occurrences)


def test_yearly_april_20th() -> None:
    event = desktop_event("毎年4月20日")
    occurrences = expander.expand(event, date(2026, 1, 1), date(2031, 12, 31))
    assert [o.date for o in occurrences] == [date(y, 4, 20) for y in range(2026, 2031)]
    assert all((o.start_time, o.duration_minutes) == (time(8, 0), 240) for o in occurrences)


SECOND_MONDAYS_2026 = [
    date(2026, 4, 13), date(2026, 5, 11), date(2026, 6, 8), date(2026, 7, 13), date(2026, 8, 10),
    date(2026, 9, 14), date(2026, 10, 12), date(2026, 11, 9), date(2026, 12, 14),
]


def test_second_monday_without_holiday_hits() -> None:
    # 入力例のカレンダーの祝日（1/1・1/12・2/11・4/29）は 4〜12 月の第 2 月曜に当たらない。
    event = desktop_event("毎月第2月曜、祝日なら前営業日へ")
    assert all(Weekday.of(d) == Weekday.MONDAY for d in SECOND_MONDAYS_2026)
    assert _dates(event, date(2026, 4, 1), date(2026, 12, 31), desktop_calendar()) == SECOND_MONDAYS_2026


def test_second_monday_on_a_holiday_moves_to_the_previous_business_day() -> None:
    # 2026 年のスポーツの日（10/12）は第 2 月曜。足すと前の営業日 10/9（金）へ寄る。
    event = desktop_event("毎月第2月曜、祝日なら前営業日へ")
    calendar = desktop_calendar((Holiday(date(2026, 10, 12), "スポーツの日"),))
    dates = _dates(event, date(2026, 4, 1), date(2026, 12, 31), calendar)
    assert date(2026, 10, 12) not in dates
    assert date(2026, 10, 9) in dates
    assert len(dates) == len(SECOND_MONDAYS_2026)


def test_skip_this_occurrence() -> None:
    event = desktop_event("この回だけスキップ")
    assert _dates(event, date(2026, 4, 20), date(2026, 5, 25)) == [
        date(2026, 4, 20), date(2026, 4, 27), date(2026, 5, 4), date(2026, 5, 18), date(2026, 5, 25)
    ]


def test_override_this_occurrence_time() -> None:
    event = desktop_event("この回だけ時間変更")
    occurrences = expander.expand(event, date(2026, 5, 1), date(2026, 5, 31))
    assert [o.date for o in occurrences] == [
        date(2026, 5, 5), date(2026, 5, 12), date(2026, 5, 19), date(2026, 5, 26)
    ]
    changed = next(o for o in occurrences if o.date == date(2026, 5, 12))
    assert changed.is_overridden
    assert (changed.title, changed.location, changed.start_time, changed.duration_minutes) == (
        "開発定例（短縮）", "会議室C", time(10, 30), 30,
    )
    others = [o for o in occurrences if o.date != date(2026, 5, 12)]
    assert all((o.title, o.start_time, o.duration_minutes) == ("開発定例", time(10, 0), 60) for o in others)


def test_move_this_occurrence() -> None:
    event = desktop_event("この回だけ移動")
    occurrences = expander.expand(event, date(2026, 4, 1), date(2026, 7, 31))
    # 第 1 月曜: 4/6・5/4・6/1（→ 6/2 15:00 へ移動）・7/6
    assert [o.date for o in occurrences] == [
        date(2026, 4, 6), date(2026, 5, 4), date(2026, 6, 2), date(2026, 7, 6)
    ]
    moved = occurrences[2]
    assert moved.is_moved
    assert (moved.title, moved.location, moved.start_time, moved.duration_minutes) == (
        "月次報告会（振替）", "会議室E", time(15, 0), 60,
    )
    assert moved.series_key == OccurrenceKey(date(2026, 6, 1), time(13, 0))


@pytest.mark.parametrize(
    "name",
    [p.stem for p in sorted(SAMPLES.glob("*.json")) if p.stem != "営業日カレンダーサンプル"],
)
def test_every_sample_loads_and_keeps_its_version(name: str) -> None:
    event = desktop_event(name)
    assert event.version == 1
    assert event.time_zone == TimeZoneId("Asia/Tokyo")
