"""Recurrence rules (ported from docs/time-model.md §10-2, §10-4).

Rules are held as structures, not RFC 5545 RRULE strings, because business-day shifting
(``AdjustmentRule``) depends on each user's holiday calendar and cannot be expressed in RRULE.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

NO_END_DATE = date.max
"""An end date of 9999-12-31 means "no end date" (same as the system it was ported from)."""


class Weekday(enum.StrEnum):
    """Weekday. Values are iCalendar abbreviations (same spelling as the original's JSON)."""

    MONDAY = "MO"
    TUESDAY = "TU"
    WEDNESDAY = "WE"
    THURSDAY = "TH"
    FRIDAY = "FR"
    SATURDAY = "SA"
    SUNDAY = "SU"

    @property
    def iso_index(self) -> int:
        """Monday 0 to Sunday 6 (same counting as ``date.weekday()``)."""
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
    # 1–5 mean "the nth", -1 means "the last". There is no 0.
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
        # Drop duplicate weekdays and sort Monday-first (keeps expansion order stable).
        normalized = tuple(sorted(set(self.weekdays), key=lambda w: w.iso_index))
        object.__setattr__(self, "weekdays", normalized)


@dataclass(frozen=True)
class DayOfMonthMonthlyRule:
    """Day n of every month. If the month has no day n (e.g. Feb 30), nothing occurs that month."""

    day: int

    def __post_init__(self) -> None:
        _check_day(self.day)


@dataclass(frozen=True)
class NthWeekdayMonthlyRule:
    """The nth <weekday> of every month (``week_index = -1`` is the last <weekday>)."""

    week_index: int
    weekday: Weekday

    def __post_init__(self) -> None:
        _check_week_index(self.week_index)


@dataclass(frozen=True)
class LastDayOfMonthMonthlyRule:
    """Last day of every month (28th–31st)."""


MonthlyRule = DayOfMonthMonthlyRule | NthWeekdayMonthlyRule | LastDayOfMonthMonthlyRule


@dataclass(frozen=True)
class DayOfMonthYearlyRule:
    """Month m, day d every year. Days missing in a year (Feb 29 in a common year) do not occur."""

    month: int
    day: int

    def __post_init__(self) -> None:
        _check_month(self.month)
        _check_day(self.day)


@dataclass(frozen=True)
class NthWeekdayYearlyRule:
    """The nth <weekday> of month m every year."""

    month: int
    week_index: int
    weekday: Weekday

    def __post_init__(self) -> None:
        _check_month(self.month)
        _check_week_index(self.week_index)


YearlyRule = DayOfMonthYearlyRule | NthWeekdayYearlyRule


class AdjustmentCondition(enum.StrEnum):
    HOLIDAY = "HOLIDAY"
    """Shift only when the candidate date is a day off (a day in the "counted as off" layers)."""
    ALWAYS = "ALWAYS"
    """Shift regardless of holidays (e.g. "3 business days before the 15th")."""


class AdjustmentShiftUnit(enum.StrEnum):
    BUSINESS_DAY = "BUSINESS_DAY"
    CALENDAR_DAY = "CALENDAR_DAY"


class AdjustmentAction(enum.StrEnum):
    SHIFT = "SHIFT"
    CANCEL = "CANCEL"
    """Occurrences that meet the condition are cancelled instead of shifted."""


@dataclass(frozen=True)
class AdjustmentRule:
    """Business-day shift. Negative ``shift_amount`` moves earlier, positive moves later.

    Business days and days off are decided by the user's 4 layers of days off (ADR-0029). No calendar is named (ADR-0032).
    """

    condition: AdjustmentCondition
    shift_unit: AdjustmentShiftUnit
    shift_amount: int
    action: AdjustmentAction = AdjustmentAction.SHIFT

    @classmethod
    def previous_business_day_on_holiday(cls) -> AdjustmentRule:
        """On a day off, move to the previous business day (the original's ``AdjustmentRule(Backward)``)."""
        return cls(AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.BUSINESS_DAY, -1)

    @classmethod
    def next_business_day_on_holiday(cls) -> AdjustmentRule:
        """On a day off, move to the next business day (the original's ``AdjustmentRule(Forward)``)."""
        return cls(AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.BUSINESS_DAY, 1)


@dataclass(frozen=True)
class RecurrenceRule:
    """The recurrence itself. Holds exactly one sub-rule matching its type."""

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
