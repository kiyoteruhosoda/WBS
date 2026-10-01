"""繰り返しの規則（移植元 docs/time-model.md §10-2・§10-4）。

規則は RFC 5545 の RRULE 文字列ではなく構造体で持つ。営業日シフト
（``AdjustmentRule``）は利用者ごとの祝日カレンダーに依存し、RRULE では表せないため。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

NO_END_DATE = date.max
"""「終了日なし」は 9999-12-31 で持つ（移植元と同じ）。"""


class Weekday(enum.StrEnum):
    """曜日。値は iCalendar の略号（移植元の JSON と同じ綴り）。"""

    MONDAY = "MO"
    TUESDAY = "TU"
    WEDNESDAY = "WE"
    THURSDAY = "TH"
    FRIDAY = "FR"
    SATURDAY = "SA"
    SUNDAY = "SU"

    @property
    def iso_index(self) -> int:
        """月曜 0 〜 日曜 6（``date.weekday()`` と同じ数え方）。"""
        return _ISO_ORDER.index(self)

    @classmethod
    def of(cls, day: date) -> Weekday:
        return _ISO_ORDER[day.weekday()]


_ISO_ORDER: tuple[Weekday, ...] = (
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
)

WEEKDAYS_MON_TO_FRI: frozenset[Weekday] = frozenset(_ISO_ORDER[:5])


class RecurrenceType(enum.StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


def _check_week_index(week_index: int) -> None:
    # 1〜5 が「第 n」、-1 が「最終」。0 は無い。
    if week_index == 0 or week_index < -1 or week_index > 5:
        raise ValidationError("week_index must be 1..5 or -1 (last)")


def _check_month(month: int) -> None:
    if not 1 <= month <= 12:
        raise ValidationError("month must be between 1 and 12")


def _check_day(day: int) -> None:
    if not 1 <= day <= 31:
        raise ValidationError("day must be between 1 and 31")


@dataclass(frozen=True)
class WeeklyRule:
    weekdays: tuple[Weekday, ...]

    def __post_init__(self) -> None:
        if not self.weekdays:
            raise ValidationError("at least one weekday is required")
        # 同じ曜日の重複は落とし、月曜始まりの順に揃える（展開の順序を安定させる）。
        normalized = tuple(sorted(set(self.weekdays), key=lambda w: w.iso_index))
        object.__setattr__(self, "weekdays", normalized)


@dataclass(frozen=True)
class DayOfMonthMonthlyRule:
    """毎月 n 日。その月に n 日が無ければ（例: 2 月 30 日）その月は発生しない。"""

    day: int

    def __post_init__(self) -> None:
        _check_day(self.day)


@dataclass(frozen=True)
class NthWeekdayMonthlyRule:
    """毎月 第 n ○曜日（``week_index = -1`` は最終○曜日）。"""

    week_index: int
    weekday: Weekday

    def __post_init__(self) -> None:
        _check_week_index(self.week_index)


@dataclass(frozen=True)
class LastDayOfMonthMonthlyRule:
    """毎月末日（28〜31 日）。"""


MonthlyRule = DayOfMonthMonthlyRule | NthWeekdayMonthlyRule | LastDayOfMonthMonthlyRule


@dataclass(frozen=True)
class DayOfMonthYearlyRule:
    """毎年 m 月 d 日。その年に無い日（2 月 29 日の平年）は発生しない。"""

    month: int
    day: int

    def __post_init__(self) -> None:
        _check_month(self.month)
        _check_day(self.day)


@dataclass(frozen=True)
class NthWeekdayYearlyRule:
    """毎年 m 月の第 n ○曜日。"""

    month: int
    week_index: int
    weekday: Weekday

    def __post_init__(self) -> None:
        _check_month(self.month)
        _check_week_index(self.week_index)


YearlyRule = DayOfMonthYearlyRule | NthWeekdayYearlyRule


class AdjustmentCondition(enum.StrEnum):
    HOLIDAY = "HOLIDAY"
    """候補日が祝日のときだけ寄せる。"""
    ALWAYS = "ALWAYS"
    """祝日かどうかに関わらず寄せる（例: 「15 日の 3 営業日前」）。"""


class AdjustmentShiftUnit(enum.StrEnum):
    BUSINESS_DAY = "BUSINESS_DAY"
    CALENDAR_DAY = "CALENDAR_DAY"


class AdjustmentAction(enum.StrEnum):
    SHIFT = "SHIFT"
    CANCEL = "CANCEL"
    """条件に当たった回は寄せずに取りやめる。"""


@dataclass(frozen=True)
class AdjustmentRule:
    """営業日シフト。``shift_amount`` が負なら前倒し、正なら後ろ倒し。"""

    condition: AdjustmentCondition
    shift_unit: AdjustmentShiftUnit
    shift_amount: int
    calendar_id: int | None = None
    action: AdjustmentAction = AdjustmentAction.SHIFT

    @classmethod
    def previous_business_day_on_holiday(cls, calendar_id: int | None = None) -> AdjustmentRule:
        """祝日なら前の営業日へ（移植元の ``AdjustmentRule(Backward)``）。"""
        return cls(AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.BUSINESS_DAY, -1, calendar_id)

    @classmethod
    def next_business_day_on_holiday(cls, calendar_id: int | None = None) -> AdjustmentRule:
        """祝日なら次の営業日へ（移植元の ``AdjustmentRule(Forward)``）。"""
        return cls(AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.BUSINESS_DAY, 1, calendar_id)


@dataclass(frozen=True)
class RecurrenceRule:
    """繰り返しの本体。種別に対応する下位規則を 1 つだけ持つ。"""

    rule_type: RecurrenceType
    interval: int
    end_date: date
    weekly: WeeklyRule | None = None
    monthly: MonthlyRule | None = None
    yearly: YearlyRule | None = None
    adjustment: AdjustmentRule | None = None

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValidationError("interval must be 1 or greater")
        required = {
            RecurrenceType.WEEKLY: self.weekly,
            RecurrenceType.MONTHLY: self.monthly,
            RecurrenceType.YEARLY: self.yearly,
        }[self.rule_type]
        if required is None:
            raise ValidationError(
                f"{self.rule_type.value.lower()} rule is required for {self.rule_type.value} recurrence"
            )

    def with_end_date(self, end_date: date) -> RecurrenceRule:
        return RecurrenceRule(
            self.rule_type, self.interval, end_date,
            self.weekly, self.monthly, self.yearly, self.adjustment,
        )


__all__ = [
    "NO_END_DATE",
    "WEEKDAYS_MON_TO_FRI",
    "AdjustmentAction",
    "AdjustmentCondition",
    "AdjustmentRule",
    "AdjustmentShiftUnit",
    "DayOfMonthMonthlyRule",
    "DayOfMonthYearlyRule",
    "LastDayOfMonthMonthlyRule",
    "MonthlyRule",
    "NthWeekdayMonthlyRule",
    "NthWeekdayYearlyRule",
    "RecurrenceRule",
    "RecurrenceType",
    "WeeklyRule",
    "Weekday",
    "YearlyRule",
]
