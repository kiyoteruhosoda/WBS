"""繰り返しの規則（``RecurrenceRule``）と素の辞書の行き来。

辞書の形は API の入出力と表の ``calendar_events.recurrence_rule``（JSON の文字列）で
共通（移植元 docs/storage.md §5 と同じく、直列化の出所を 1 つにする）::

    {
      "type": "WEEKLY" | "MONTHLY" | "YEARLY",
      "interval": 1,
      "end_date": "2026-12-31" | null,          # null は終了日なし（9999-12-31）
      "weekly":  {"weekdays": ["MO", "WE"]} | null,
      "monthly": {"kind": "DAY_OF_MONTH", "day": 15}
               | {"kind": "NTH_WEEKDAY", "week_index": 2, "weekday": "TU"}   # -1 は最終
               | {"kind": "LAST_DAY"} | null,
      "yearly":  {"kind": "DAY_OF_MONTH", "month": 1, "day": 1}
               | {"kind": "NTH_WEEKDAY", "month": 1, "week_index": 2, "weekday": "MO"} | null,
      "adjustment": {"condition": "HOLIDAY" | "ALWAYS",
                     "shift_unit": "BUSINESS_DAY" | "CALENDAR_DAY",
                     "shift_amount": -1, "calendar_id": 3 | null,
                     "action": "SHIFT" | "CANCEL"} | null
    }

⚠ 表に入った形でもあるので、キーを変えるときは移行（Alembic のデータ移行）を伴う。
読めない形は ``ValidationError``。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Any

from src.domain.exceptions import ValidationError
from src.domain.value_objects.recurrence import (
    NO_END_DATE,
    AdjustmentAction,
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

DAY_OF_MONTH = "DAY_OF_MONTH"
NTH_WEEKDAY = "NTH_WEEKDAY"
LAST_DAY = "LAST_DAY"


# ── 規則 → 辞書 ─────────────────────────────────────────────────────────────


def recurrence_rule_to_mapping(rule: RecurrenceRule) -> dict[str, Any]:
    return {
        "type": rule.rule_type.value,
        "interval": rule.interval,
        "end_date": None if rule.end_date == NO_END_DATE else rule.end_date.isoformat(),
        "weekly": (
            {"weekdays": [w.value for w in rule.weekly.weekdays]} if rule.weekly else None
        ),
        "monthly": _monthly_to_mapping(rule.monthly) if rule.monthly else None,
        "yearly": _yearly_to_mapping(rule.yearly) if rule.yearly else None,
        "adjustment": _adjustment_to_mapping(rule.adjustment) if rule.adjustment else None,
    }


def _monthly_to_mapping(monthly: MonthlyRule) -> dict[str, Any]:
    if isinstance(monthly, DayOfMonthMonthlyRule):
        return {"kind": DAY_OF_MONTH, "day": monthly.day}
    if isinstance(monthly, NthWeekdayMonthlyRule):
        return {
            "kind": NTH_WEEKDAY,
            "week_index": monthly.week_index,
            "weekday": monthly.weekday.value,
        }
    return {"kind": LAST_DAY}


def _yearly_to_mapping(yearly: YearlyRule) -> dict[str, Any]:
    if isinstance(yearly, DayOfMonthYearlyRule):
        return {"kind": DAY_OF_MONTH, "month": yearly.month, "day": yearly.day}
    return {
        "kind": NTH_WEEKDAY,
        "month": yearly.month,
        "week_index": yearly.week_index,
        "weekday": yearly.weekday.value,
    }


def _adjustment_to_mapping(adjustment: AdjustmentRule) -> dict[str, Any]:
    return {
        "condition": adjustment.condition.value,
        "shift_unit": adjustment.shift_unit.value,
        "shift_amount": adjustment.shift_amount,
        "calendar_id": adjustment.calendar_id,
        "action": adjustment.action.value,
    }


# ── 辞書 → 規則 ─────────────────────────────────────────────────────────────


def recurrence_rule_from_mapping(data: Mapping[str, Any]) -> RecurrenceRule:
    end_date_text = data.get("end_date")
    return RecurrenceRule(
        rule_type=_enum(RecurrenceType, _required(data, "type"), "type"),
        interval=_int(data.get("interval", 1), "interval"),
        end_date=NO_END_DATE if end_date_text is None else _date(end_date_text, "end_date"),
        weekly=_weekly_from(data.get("weekly")),
        monthly=_monthly_from(data.get("monthly")),
        yearly=_yearly_from(data.get("yearly")),
        adjustment=_adjustment_from(data.get("adjustment")),
    )


def _weekly_from(data: Mapping[str, Any] | None) -> WeeklyRule | None:
    if data is None:
        return None
    weekdays = _required(data, "weekdays")
    if not isinstance(weekdays, list | tuple):
        raise ValidationError("weekly.weekdays must be a list")
    return WeeklyRule(tuple(_enum(Weekday, w, "weekly.weekdays") for w in weekdays))


def _monthly_from(data: Mapping[str, Any] | None) -> MonthlyRule | None:
    if data is None:
        return None
    kind = _required(data, "kind")
    if kind == DAY_OF_MONTH:
        return DayOfMonthMonthlyRule(_int(_required(data, "day"), "monthly.day"))
    if kind == NTH_WEEKDAY:
        return NthWeekdayMonthlyRule(
            _int(_required(data, "week_index"), "monthly.week_index"),
            _enum(Weekday, _required(data, "weekday"), "monthly.weekday"),
        )
    if kind == LAST_DAY:
        return LastDayOfMonthMonthlyRule()
    raise ValidationError(f"unknown monthly.kind: {kind}")


def _yearly_from(data: Mapping[str, Any] | None) -> YearlyRule | None:
    if data is None:
        return None
    kind = _required(data, "kind")
    month = _int(_required(data, "month"), "yearly.month")
    if kind == DAY_OF_MONTH:
        return DayOfMonthYearlyRule(month, _int(_required(data, "day"), "yearly.day"))
    if kind == NTH_WEEKDAY:
        return NthWeekdayYearlyRule(
            month,
            _int(_required(data, "week_index"), "yearly.week_index"),
            _enum(Weekday, _required(data, "weekday"), "yearly.weekday"),
        )
    raise ValidationError(f"unknown yearly.kind: {kind}")


def _adjustment_from(data: Mapping[str, Any] | None) -> AdjustmentRule | None:
    if data is None:
        return None
    calendar_id = data.get("calendar_id")
    return AdjustmentRule(
        condition=_enum(AdjustmentCondition, _required(data, "condition"), "adjustment.condition"),
        shift_unit=_enum(
            AdjustmentShiftUnit, _required(data, "shift_unit"), "adjustment.shift_unit"
        ),
        shift_amount=_int(_required(data, "shift_amount"), "adjustment.shift_amount"),
        calendar_id=None if calendar_id is None else _int(calendar_id, "adjustment.calendar_id"),
        action=_enum(AdjustmentAction, data.get("action", "SHIFT"), "adjustment.action"),
    )


def _required(data: Mapping[str, Any], key: str) -> Any:
    if data.get(key) is None:
        raise ValidationError(f"{key} is required")
    return data[key]


def _enum[E: StrEnum](
    enum_type: type[E], value: Any, label: str
) -> E:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValidationError(f"invalid {label}: {value!r}") from exc


def _int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be an integer")
    return value


def _date(value: Any, label: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid {label}: {value!r}") from exc


__all__ = ["recurrence_rule_from_mapping", "recurrence_rule_to_mapping"]
