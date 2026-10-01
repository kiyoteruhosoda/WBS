"""壁時計 ⇔ UTC の瞬間（移植元 CoreTests/LocalSchedulePointTests.cs）。

移植元の ``EndInstant``（壁時計で終わりを出す）は持ってこなかったので、
``Duration_IsWallClock_AcrossSpringForward`` は写さない。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from src.domain.value_objects.local_schedule_point import (
    local_date_of,
    local_time_of,
    start_instant,
    to_naive_utc,
    wrapping_duration_minutes,
)
from tests.unit.domain.scheduling.support import NEW_YORK, TOKYO


def _instant(y: int, m: int, d: int, h: int, mi: int, zone) -> datetime:
    return start_instant(date(y, m, d), time(h, mi), zone.zone)


def test_jst_wall_clock_resolves_to_fixed_utc_instant() -> None:
    assert _instant(2026, 6, 15, 10, 0, TOKYO) == datetime(2026, 6, 15, 1, 0)


def test_jst_reservation_shown_in_new_york_has_different_wall_clock() -> None:
    instant = _instant(2026, 6, 15, 10, 0, TOKYO)
    assert local_date_of(instant, NEW_YORK.zone) == date(2026, 6, 14)
    assert local_time_of(instant, NEW_YORK.zone) == time(21, 0)


def test_jst_reservation_shown_in_new_york_differs_between_summer_and_winter() -> None:
    summer = local_time_of(_instant(2026, 7, 1, 10, 0, TOKYO), NEW_YORK.zone)
    winter = local_time_of(_instant(2026, 1, 15, 10, 0, TOKYO), NEW_YORK.zone)
    assert summer == time(21, 0)  # EDT
    assert winter == time(20, 0)  # EST


def test_new_york_wall_clock_keeps_local_time_but_shifts_one_hour_in_tokyo() -> None:
    summer = _instant(2026, 7, 1, 9, 0, NEW_YORK)
    winter = _instant(2026, 1, 15, 9, 0, NEW_YORK)
    assert summer == datetime(2026, 7, 1, 13, 0)
    assert winter == datetime(2026, 1, 15, 14, 0)
    assert local_time_of(summer, NEW_YORK.zone) == time(9, 0)
    assert local_time_of(winter, NEW_YORK.zone) == time(9, 0)
    assert local_time_of(summer, TOKYO.zone) == time(22, 0)
    assert local_time_of(winter, TOKYO.zone) == time(23, 0)


def test_aware_instant_is_read_as_its_utc_moment() -> None:
    aware = datetime(2026, 6, 15, 1, 0, tzinfo=UTC)
    assert to_naive_utc(aware) == datetime(2026, 6, 15, 1, 0)
    assert local_time_of(aware, TOKYO.zone) == time(10, 0)


def test_wrapping_duration() -> None:
    assert wrapping_duration_minutes(time(10, 0), time(11, 30)) == 90
    assert wrapping_duration_minutes(time(23, 0), time(2, 0)) == 180  # 日をまたぐ
    assert wrapping_duration_minutes(time(9, 0), time(9, 0)) == 1440  # 同じ時刻は 24 時間
