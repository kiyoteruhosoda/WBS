"""日本の祝日・休日を暦から出す（「国民の祝日に関する法律」、ADR-0009）。

実行時に外へ取りに行かない（内閣府の CSV などを引かない）。規則で決まるものは規則で、
法律で 1 年だけ動かした日（2019 年の即位・2020/2021 年の五輪）は表で持つ。

- 春分の日・秋分の日は、毎年 2 月の官報で翌年の日が決まる。ここでは 1980〜2099 年に
  当てはまる近似式で出す（実際の公示と食い違ったことは今のところ無い）。
- 振替休日: 祝日が日曜なら、その後の最も近い祝日でない日。
- 国民の休日: 前日と翌日が祝日（振替休日を除く）で、それ自体は祝日でない日。

扱う年は 2007 年（振替休日・国民の休日の今の規則と「昭和の日」が始まった年）から
2099 年（春分・秋分の式が当てはまる最後の年）まで。外れは ``ValidationError``。
法律が変わったときや公示と食い違ったときは、営業日カレンダーの祝日を手で直す。
"""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.entities.business_calendar import Holiday
from src.domain.exceptions import ValidationError

FIRST_SUPPORTED_YEAR = 2007
LAST_SUPPORTED_YEAR = 2099

SUBSTITUTE_HOLIDAY = "振替休日"
CITIZENS_HOLIDAY = "国民の休日"

_MONDAY = 0
_SUNDAY = 6

# 法律（特措法）でその年だけ動かした・足した祝日。名前 → 日付（その年に無いものは None）。
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
    """その年の「国民の祝日」（振替休日・国民の休日を除く）。"""
    special = _SPECIAL_YEARS.get(year, {})

    def moved(name: str, usual: date | None) -> date | None:
        return special[name] if name in special else usual

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
    """``year`` 年の祝日・振替休日・国民の休日を日付順に返す。"""
    if not FIRST_SUPPORTED_YEAR <= year <= LAST_SUPPORTED_YEAR:
        raise ValidationError(
            f"japanese holidays are available for {FIRST_SUPPORTED_YEAR}..{LAST_SUPPORTED_YEAR}"
        )
    statutory = _statutory_holidays(year)
    holidays = dict(statutory)

    one_day = timedelta(days=1)
    for day in sorted(statutory):
        # 国民の休日: 祝日に挟まれた祝日でない日。
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
    "FIRST_SUPPORTED_YEAR",
    "LAST_SUPPORTED_YEAR",
    "SUBSTITUTE_HOLIDAY",
    "japanese_national_holidays",
]
