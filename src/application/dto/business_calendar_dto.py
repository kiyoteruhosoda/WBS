from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday


@dataclass
class CreateBusinessCalendarCommand:
    user_id: int
    name: str
    time_zone: str
    workdays: frozenset[Weekday] = field(default_factory=lambda: WEEKDAYS_MON_TO_FRI)
    shift_on_holidays_only: bool = False
    is_enabled: bool = True


@dataclass
class UpdateBusinessCalendarCommand:
    calendar_id: int
    user_id: int
    name: str
    workdays: frozenset[Weekday]
    shift_on_holidays_only: bool = False
    is_enabled: bool = True
