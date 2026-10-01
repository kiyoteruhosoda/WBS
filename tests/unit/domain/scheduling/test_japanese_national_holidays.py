"""日本の祝日を暦から出す（ADR-0009）。期待値は内閣府の「国民の祝日」の一覧から写した。"""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.exceptions import ValidationError
from src.domain.services.japanese_national_holidays import (
    CITIZENS_HOLIDAY,
    SUBSTITUTE_HOLIDAY,
    japanese_national_holidays,
)


def _as_dict(year: int) -> dict[date, str | None]:
    return {h.date: h.name for h in japanese_national_holidays(year)}


def test_2026_matches_the_cabinet_office_list() -> None:
    assert _as_dict(2026) == {
        date(2026, 1, 1): "元日",
        date(2026, 1, 12): "成人の日",
        date(2026, 2, 11): "建国記念の日",
        date(2026, 2, 23): "天皇誕生日",
        date(2026, 3, 20): "春分の日",
        date(2026, 4, 29): "昭和の日",
        date(2026, 5, 3): "憲法記念日",
        date(2026, 5, 4): "みどりの日",
        date(2026, 5, 5): "こどもの日",
        date(2026, 5, 6): SUBSTITUTE_HOLIDAY,  # 5/3 が日曜
        date(2026, 7, 20): "海の日",
        date(2026, 8, 11): "山の日",
        date(2026, 9, 21): "敬老の日",
        date(2026, 9, 22): CITIZENS_HOLIDAY,  # 敬老の日と秋分の日に挟まれる
        date(2026, 9, 23): "秋分の日",
        date(2026, 10, 12): "スポーツの日",
        date(2026, 11, 3): "文化の日",
        date(2026, 11, 23): "勤労感謝の日",
    }


def test_holidays_are_returned_in_date_order() -> None:
    days = [h.date for h in japanese_national_holidays(2026)]
    assert days == sorted(days)


def test_2019_has_the_enthronement_days_and_no_emperors_birthday() -> None:
    holidays = _as_dict(2019)
    assert holidays[date(2019, 4, 30)] == CITIZENS_HOLIDAY
    assert holidays[date(2019, 5, 1)] == "天皇の即位の日"
    assert holidays[date(2019, 5, 2)] == CITIZENS_HOLIDAY
    assert holidays[date(2019, 5, 6)] == SUBSTITUTE_HOLIDAY  # 5/5 が日曜
    assert holidays[date(2019, 10, 14)] == "体育の日"
    assert holidays[date(2019, 10, 22)] == "即位礼正殿の儀の行われる日"
    assert "天皇誕生日" not in holidays.values()
    assert len(holidays) == 22


def test_2021_olympic_moves() -> None:
    holidays = _as_dict(2021)
    assert holidays[date(2021, 7, 22)] == "海の日"
    assert holidays[date(2021, 7, 23)] == "スポーツの日"
    assert holidays[date(2021, 8, 8)] == "山の日"
    assert holidays[date(2021, 8, 9)] == SUBSTITUTE_HOLIDAY
    for usual in (date(2021, 7, 19), date(2021, 8, 11), date(2021, 10, 11)):
        assert usual not in holidays


def test_emperors_birthday_moved_from_december_to_february() -> None:
    assert _as_dict(2018)[date(2018, 12, 23)] == "天皇誕生日"
    assert _as_dict(2018)[date(2018, 12, 24)] == SUBSTITUTE_HOLIDAY  # 12/23 が日曜
    assert _as_dict(2020)[date(2020, 2, 23)] == "天皇誕生日"
    assert _as_dict(2020)[date(2020, 2, 24)] == SUBSTITUTE_HOLIDAY


@pytest.mark.parametrize(
    ("year", "vernal", "autumnal"),
    [(2019, 21, 23), (2024, 20, 22), (2025, 20, 23), (2026, 20, 23), (2027, 21, 23)],
)
def test_equinox_days(year: int, vernal: int, autumnal: int) -> None:
    holidays = _as_dict(year)
    assert holidays[date(year, 3, vernal)] == "春分の日"
    assert holidays[date(year, 9, autumnal)] == "秋分の日"


@pytest.mark.parametrize("year", [2006, 2100])
def test_years_outside_the_supported_range_are_refused(year: int) -> None:
    with pytest.raises(ValidationError):
        japanese_national_holidays(year)
