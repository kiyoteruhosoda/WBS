"""Derive Japanese national holidays and substitute days off from the calendar ("Act on National Holidays", ADR-0009).

Nothing is fetched at runtime (no Cabinet Office CSV or the like). What follows rules is computed by rule;
days moved by law for a single year (the 2019 enthronement, the 2020/2021 Olympics) are kept in a table.

- Vernal and Autumnal Equinox Days are fixed for the next year in the official gazette each February. Here they come from an
  approximation valid for 1980–2099 (it has not disagreed with the official announcements so far).
- Substitute holiday: if a national holiday falls on Sunday, the nearest following day that is not a holiday.
- Citizens' holiday: a non-holiday day whose previous and next days are both national holidays (excluding substitute holidays).

Supported years run from 2007 (when the current substitute/citizens' holiday rules and "Showa Day" began) to
2099 (the last year the equinox formulas hold). Outside that: ``ValidationError``.
When the law changes or a date disagrees with the announcement, fix the days in the "Japanese holidays" layer (ADR-0029) by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.domain.exceptions import ValidationError

FIRST_SUPPORTED_YEAR = 2007
LAST_SUPPORTED_YEAR = 2099

SUBSTITUTE_HOLIDAY = "振替休日"
CITIZENS_HOLIDAY = "国民の休日"



@dataclass(frozen=True)
class Holiday:
    """One national holiday / day off derived from the calendar (source for the "Japanese holidays" layer)."""

    date: date
    name: str


_MONDAY = 0
_SUNDAY = 6

# Holidays moved or added by law (special measures acts) for that year only. Name → date (None if absent that year).
_SPECIAL_YEARS: dict[int, dict[str, date | None]] = {
    2019: {
        "天皇の即位の日": date(2019, 5, 1),
        "即位礼正殿の儀の行われる日": date(2019, 10, 22),
    },
    2020: {"海の日": date(2020, 7, 23), "スポーツの日": date(2020, 7, 24), "山の日": date(2020, 8, 10)},
    2021: {"海の日": date(2021, 7, 22), "スポーツの日": date(2021, 7, 23), "山の日": date(2021, 8, 8)},
}


def _nth_monday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (_MONDAY - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _vernal_equinox_day(year: int) -> int:
    return int(20.8431 + 0.242194 * (year - 1980) - (year - 1980) // 4)


def _autumnal_equinox_day(year: int) -> int:
    return int(23.2488 + 0.242194 * (year - 1980) - (year - 1980) // 4)


def _statutory_holidays(year: int) -> dict[date, str]:
    """That year's "national holidays" (excluding substitute holidays and citizens' holidays)."""
    special = _SPECIAL_YEARS.get(year, {})

    def moved(name: str, usual: date | None) -> date | None:
        return special.get(name, usual)

    sports_day_name = "スポーツの日" if year >= 2020 else "体育の日"
    candidates: list[tuple[str, date | None]] = [
        ("元日", date(year, 1, 1)),
        ("成人の日", _nth_monday(year, 1, 2)),
        ("建国記念の日", date(year, 2, 11)),
        ("天皇誕生日", date(year, 2, 23) if year >= 2020 else (date(year, 12, 23) if year <= 2018 else None)),
        ("春分の日", date(year, 3, _vernal_equinox_day(year))),
        ("昭和の日", date(year, 4, 29)),
        ("憲法記念日", date(year, 5, 3)),
        ("みどりの日", date(year, 5, 4)),
        ("こどもの日", date(year, 5, 5)),
        ("海の日", moved("海の日", _nth_monday(year, 7, 3))),
        ("山の日", moved("山の日", date(year, 8, 11) if year >= 2016 else None)),
        ("敬老の日", _nth_monday(year, 9, 3)),
        ("秋分の日", date(year, 9, _autumnal_equinox_day(year))),
        (sports_day_name, moved(sports_day_name, _nth_monday(year, 10, 2))),
        ("文化の日", date(year, 11, 3)),
        ("勤労感謝の日", date(year, 11, 23)),
    ]
    for name, day in special.items():
        if name not in {n for n, _ in candidates}:
            candidates.append((name, day))
    return {day: name for name, day in candidates if day is not None}


def japanese_national_holidays(year: int) -> list[Holiday]:
    """Return the national holidays, substitute holidays and citizens' holidays of ``year`` in date order."""
    if not FIRST_SUPPORTED_YEAR <= year <= LAST_SUPPORTED_YEAR:
        raise ValidationError(
            f"japanese holidays are available for {FIRST_SUPPORTED_YEAR}..{LAST_SUPPORTED_YEAR}"
        )
    statutory = _statutory_holidays(year)
    holidays = dict(statutory)

    one_day = timedelta(days=1)
    for day in sorted(statutory):
        # Citizens' holiday: a non-holiday day sandwiched between national holidays.
        between = day + one_day
        if between not in statutory and between + one_day in statutory and between.year == year:
            holidays[between] = CITIZENS_HOLIDAY
    for day in sorted(statutory):
        if day.weekday() != _SUNDAY:
            continue
        substitute = day + one_day
        while substitute in statutory:
            substitute += one_day
        if substitute.year == year:
            holidays.setdefault(substitute, SUBSTITUTE_HOLIDAY)

    return [Holiday(day, name) for day, name in sorted(holidays.items())]


__all__ = [
    "CITIZENS_HOLIDAY",
    "Holiday",
    "FIRST_SUPPORTED_YEAR",
    "LAST_SUPPORTED_YEAR",
    "SUBSTITUTE_HOLIDAY",
    "japanese_national_holidays",
]
