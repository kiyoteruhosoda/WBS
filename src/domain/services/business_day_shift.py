"""営業日シフト（移植元 ``BusinessDayShiftService``）。"""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.entities.business_calendar import BusinessCalendar
from src.domain.value_objects.recurrence import (
    AdjustmentAction,
    AdjustmentCondition,
    AdjustmentRule,
    AdjustmentShiftUnit,
)


class BusinessDayShiftService:
    def matches(self, day: date, rule: AdjustmentRule, calendar: BusinessCalendar) -> bool:
        """規則の条件に当たる日か（祝日のときだけ／いつでも）。"""
        if rule.condition == AdjustmentCondition.HOLIDAY:
            return calendar.is_holiday(day)
        return rule.condition == AdjustmentCondition.ALWAYS

    def cancels(self, day: date, rule: AdjustmentRule, calendar: BusinessCalendar) -> bool:
        """その回を取りやめるか。"""
        return rule.action == AdjustmentAction.CANCEL and self.matches(day, rule, calendar)

    def shift(self, day: date, rule: AdjustmentRule, calendar: BusinessCalendar) -> date:
        """寄せた先の日。条件に当たらなければ ``day`` のまま。"""
        if rule.action != AdjustmentAction.SHIFT or not self.matches(day, rule, calendar):
            return day
        if rule.shift_amount == 0:
            return day
        if rule.shift_unit == AdjustmentShiftUnit.BUSINESS_DAY:
            return calendar.shift_business_days(day, rule.shift_amount)
        return day + timedelta(days=rule.shift_amount)


__all__ = ["BusinessDayShiftService"]
