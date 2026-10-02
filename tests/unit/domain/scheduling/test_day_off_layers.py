"""休みの 4 層と営業日の判定（task #191、ADR-0029）。

営業日 = 営業日の層の曜日に当たり、「休みとして数える」の付いた日付の一覧の層のどれにも無い日。
2026-10-05 は月曜、10-12 は月曜で日本の祝日（スポーツの日）。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.entities.calendar import Calendar, DayOffReason
from src.domain.entities.day_off import DayOff
from src.domain.exceptions import ValidationError
from src.domain.services.day_off_layers import WEEKLY_REASON, DayOffLayers
from src.domain.value_objects.recurrence import Weekday

NOW = datetime(2026, 10, 1)
USER = 1


def _layer(calendar_id: int, reason: DayOffReason | None, *, counts: bool = True, workdays=None) -> Calendar:
    layer = Calendar.create_layer(USER, reason, NOW, workdays=workdays)
    layer.id = calendar_id
    if reason is not None:
        layer.counts_as_day_off = counts
    return layer


WORKWEEK, COMPANY, PERSONAL, NATIONAL = 10, 11, 12, 13


def _layers(*, counts: dict[int, bool] | None = None, workdays=None) -> DayOffLayers:
    counts = counts or {}
    calendars = [
        _layer(WORKWEEK, None, workdays=workdays),
        _layer(COMPANY, DayOffReason.COMPANY, counts=counts.get(COMPANY, True)),
        _layer(PERSONAL, DayOffReason.PERSONAL, counts=counts.get(PERSONAL, True)),
        _layer(NATIONAL, DayOffReason.NATIONAL_HOLIDAY, counts=counts.get(NATIONAL, True)),
    ]
    days = [
        DayOff(NATIONAL, date(2026, 10, 12), "スポーツの日"),
        DayOff(COMPANY, date(2026, 12, 29), "年末年始"),
        DayOff(PERSONAL, date(2026, 10, 7), None),
        DayOff(PERSONAL, date(2026, 10, 12), "旅行"),
    ]
    return DayOffLayers.of(calendars, days)


def test_new_layers_count_as_days_off_and_the_workweek_is_monday_to_friday() -> None:
    workweek = Calendar.create_layer(USER, None, NOW)
    personal = Calendar.create_layer(USER, DayOffReason.PERSONAL, NOW)
    assert workweek.workdays == frozenset(
        {Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY}
    )
    assert (personal.counts_as_day_off, personal.holds_events, workweek.holds_events) == (True, False, False)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 5), True),  # 月曜・何も無い
        (date(2026, 10, 10), False),  # 土曜（曜日の休み）
        (date(2026, 10, 7), False),  # 私の休み
        (date(2026, 10, 12), False),  # 祝日 ＋ 私の休み
        (date(2026, 12, 29), False),  # 会社の公休
    ],
)
def test_business_day_combines_all_layers(day: date, expected: bool) -> None:
    assert _layers().is_business_day(day) is expected


def test_a_layer_that_does_not_count_leaves_its_days_as_business_days() -> None:
    layers = _layers(counts={PERSONAL: False})
    assert layers.is_business_day(date(2026, 10, 7)) is True
    # 同じ日に数える層（祝日）があれば休みのまま
    assert layers.is_business_day(date(2026, 10, 12)) is False
    assert _layers(counts={PERSONAL: False, NATIONAL: False}).is_business_day(date(2026, 10, 12)) is True


def test_workweek_rule_decides_the_weekdays() -> None:
    layers = _layers(workdays={Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY})
    assert layers.is_business_day(date(2026, 10, 9)) is False  # 金曜は稼働しない
    assert layers.is_business_day(date(2026, 10, 8)) is True


def test_business_days_between_counts_both_ends() -> None:
    # 10/5(月)〜10/16(金): 平日 10 日 − 私の休み 10/7 − 祝日 10/12 = 8
    assert _layers().business_days_between(date(2026, 10, 5), date(2026, 10, 16)) == 8
    assert _layers().business_days_between(date(2026, 10, 16), date(2026, 10, 5)) == 0


def test_marks_list_every_reason_of_a_day() -> None:
    marks = _layers(counts={PERSONAL: False}).marks_between(date(2026, 10, 10), date(2026, 10, 12))
    assert [(m.day.day, m.reason, m.name, m.counts_as_day_off) for m in marks] == [
        (10, WEEKLY_REASON, None, True),
        (11, WEEKLY_REASON, None, True),
        (12, "PERSONAL", "旅行", False),
        (12, "NATIONAL_HOLIDAY", "スポーツの日", True),
    ]


def test_shift_business_days_skips_counted_days_and_weekly_days_off() -> None:
    layers = _layers(counts={COMPANY: False})
    assert layers.is_counted_day_off(date(2026, 10, 7))
    assert not layers.is_counted_day_off(date(2026, 12, 29))
    # 10/6(火) の次の営業日は 10/8(木)（10/7 は私の休み）
    assert layers.shift_business_days(date(2026, 10, 6), 1) == date(2026, 10, 8)
    # 10/13(火) の前の営業日は 10/9(金)（10/12 は祝日、10/10・11 は曜日の休み）
    assert layers.shift_business_days(date(2026, 10, 13), -1) == date(2026, 10, 9)
    assert layers.shift_business_days(date(2026, 10, 10), 0) == date(2026, 10, 10)


def test_shift_without_workdays_is_refused() -> None:
    with pytest.raises(ValidationError):
        _layers(workdays=frozenset()).shift_business_days(date(2026, 10, 6), 1)
