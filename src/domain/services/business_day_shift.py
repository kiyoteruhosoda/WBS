"""営業日シフト（移植元 ``BusinessDayShiftService``）。

営業日・休みの日は休みの 4 層（``DayOffLayers``、ADR-0029）で決まる。「祝日のときだけ」の条件は
「休みとして数える」層の日（会社の公休・私の休み・日本の祝日）に当たるとき。
"""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.services.day_off_layers import DayOffLayers
from src.domain.value_objects.recurrence import (
    AdjustmentAction,
    AdjustmentCondition,
    AdjustmentRule,
    AdjustmentShiftUnit,
)


class BusinessDayShiftService:
    def matches(self, day: date, rule: AdjustmentRule, layers: DayOffLayers) -> bool:
        """規則の条件に当たる日か（休みの日のときだけ／いつでも）。"""
        if rule.condition == AdjustmentCondition.HOLIDAY:
            return layers.is_counted_day_off(day)
        return rule.condition == AdjustmentCondition.ALWAYS

    def cancels(self, day: date, rule: AdjustmentRule, layers: DayOffLayers) -> bool:
        """その回を取りやめるか。"""
        return rule.action == AdjustmentAction.CANCEL and self.matches(day, rule, layers)

    def shift(self, day: date, rule: AdjustmentRule, layers: DayOffLayers) -> date:
        """寄せた先の日。条件に当たらなければ ``day`` のまま。"""
        if rule.action != AdjustmentAction.SHIFT or not self.matches(day, rule, layers):
            return day
        if rule.shift_amount == 0:
            return day
        if rule.shift_unit == AdjustmentShiftUnit.BUSINESS_DAY:
            return layers.shift_business_days(day, rule.shift_amount)
        return day + timedelta(days=rule.shift_amount)


__all__ = ["BusinessDayShiftService"]
