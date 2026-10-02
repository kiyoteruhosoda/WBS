"""繰り返しの規則と辞書の行き来（API の入出力と表の JSON 列で共通の形、ADR-0009）。"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.application.recurrence_rule_mapping import (
    recurrence_rule_from_mapping,
    recurrence_rule_to_mapping,
)
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
    NthWeekdayMonthlyRule,
    NthWeekdayYearlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
)

RULES = [
    RecurrenceRule(
        RecurrenceType.WEEKLY, 2, date(2026, 12, 31),
        weekly=WeeklyRule((Weekday.WEDNESDAY, Weekday.MONDAY)),
    ),
    RecurrenceRule(RecurrenceType.MONTHLY, 1, NO_END_DATE, monthly=DayOfMonthMonthlyRule(31)),
    RecurrenceRule(
        RecurrenceType.MONTHLY, 1, NO_END_DATE,
        monthly=NthWeekdayMonthlyRule(-1, Weekday.FRIDAY),
    ),
    RecurrenceRule(
        RecurrenceType.MONTHLY, 3, NO_END_DATE,
        monthly=LastDayOfMonthMonthlyRule(),
        adjustment=AdjustmentRule(
            AdjustmentCondition.ALWAYS, AdjustmentShiftUnit.BUSINESS_DAY, -3,
            AdjustmentAction.SHIFT,
        ),
    ),
    RecurrenceRule(RecurrenceType.YEARLY, 1, NO_END_DATE, yearly=DayOfMonthYearlyRule(2, 29)),
    RecurrenceRule(
        RecurrenceType.YEARLY, 1, date(2030, 1, 1),
        yearly=NthWeekdayYearlyRule(1, 2, Weekday.MONDAY),
        adjustment=AdjustmentRule(
            AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.CALENDAR_DAY, 1,
            AdjustmentAction.CANCEL,
        ),
    ),
]


@pytest.mark.parametrize("rule", RULES)
def test_round_trip_through_json(rule: RecurrenceRule) -> None:
    text = json.dumps(recurrence_rule_to_mapping(rule))
    assert recurrence_rule_from_mapping(json.loads(text)) == rule


def test_no_end_date_is_null() -> None:
    mapping = recurrence_rule_to_mapping(RULES[1])
    assert mapping["end_date"] is None
    assert mapping["monthly"] == {"kind": "DAY_OF_MONTH", "day": 31}


def test_adjustment_names_no_calendar() -> None:
    # 古い営業日カレンダーの名指しは畳んだ（ADR-0032）。書かず、古い入力に残っていても読み捨てる
    mapping = recurrence_rule_to_mapping(RULES[4])
    assert "calendar_id" not in mapping["adjustment"]
    mapping["adjustment"]["calendar_id"] = 3
    assert recurrence_rule_from_mapping(mapping) == RULES[4]


def test_weekdays_are_written_monday_first() -> None:
    assert recurrence_rule_to_mapping(RULES[0])["weekly"] == {"weekdays": ["MO", "WE"]}


@pytest.mark.parametrize(
    "data",
    [
        {"type": "WEEKLY", "interval": 1},  # weekly が無い
        {"type": "DAILY", "interval": 1},
        {"type": "MONTHLY", "monthly": {"kind": "NTH_WEEKDAY", "week_index": 2}},
        {"type": "MONTHLY", "monthly": {"kind": "SOMETIMES"}},
        {"type": "WEEKLY", "weekly": {"weekdays": ["XX"]}},
        {"type": "WEEKLY", "interval": "1", "weekly": {"weekdays": ["MO"]}},
        {"type": "WEEKLY", "end_date": "2026-13-01", "weekly": {"weekdays": ["MO"]}},
    ],
)
def test_malformed_mapping_is_a_validation_error(data: dict) -> None:
    with pytest.raises(ValidationError):
        recurrence_rule_from_mapping(data)
