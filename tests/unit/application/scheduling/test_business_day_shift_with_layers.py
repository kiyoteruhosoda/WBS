"""営業日シフトは休みの 4 層で決まる（task #191、ADR-0029）。

毎週月曜 9:00 の繰り返しに「祝日（休み）なら次の営業日」。2026-10-12（月）は日本の祝日、
10-13（火）を私の休みにすると、10-12 の回は 10-14（水）へ寄る。私の休みを数えないなら 10-13。
"""

from __future__ import annotations

from datetime import date, datetime

from src.application.dto.calendar_event_dto import CreateRecurringEventCommand
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.domain.entities.calendar import Calendar, DayOffReason
from src.domain.entities.day_off import DayOff
from src.domain.services.day_off_layers import DayOffLayers
from src.domain.value_objects.recurrence import AdjustmentRule, Weekday
from tests.unit.application.scheduling.fakes import (
    FakeClock,
    FakeTasks,
    InMemoryBusinessCalendarRepository,
    InMemoryCalendarEventRepository,
    RecordingUnitOfWork,
)
from tests.unit.domain.scheduling.support import utc, weekly_rule

USER = 1
NOW = datetime(2026, 10, 1)


class FixedLayers:
    def __init__(self, layers: DayOffLayers) -> None:
        self.layers = layers
        self.asked: list[int] = []

    def layers_for(self, user_id: int) -> DayOffLayers:
        self.asked.append(user_id)
        return self.layers


def _layers(*, personal_counts: bool) -> DayOffLayers:
    national = Calendar.create_layer(USER, DayOffReason.NATIONAL_HOLIDAY, NOW)
    national.id = 2
    personal = Calendar.create_layer(USER, DayOffReason.PERSONAL, NOW)
    personal.id = 3
    personal.counts_as_day_off = personal_counts
    workweek = Calendar.create_layer(USER, None, NOW)
    workweek.id = 1
    return DayOffLayers.of(
        [workweek, national, personal],
        [DayOff(2, date(2026, 10, 12), "スポーツの日"), DayOff(3, date(2026, 10, 13), None)],
    )


def _dates(personal_counts: bool) -> list[date]:
    source = FixedLayers(_layers(personal_counts=personal_counts))
    uc = CalendarEventUseCases(
        InMemoryCalendarEventRepository(), InMemoryBusinessCalendarRepository(), FakeTasks({}),
        RecordingUnitOfWork(), now=FakeClock(NOW), day_off_layers=source,
    )
    uc.create_recurring_event(
        CreateRecurringEventCommand(
            user_id=USER, title="週次", time_zone="Asia/Tokyo",
            anchor_utc=utc(2026, 10, 5, 9, 0), duration_minutes=60,
            recurrence_rule=weekly_rule(
                Weekday.MONDAY, adjustment=AdjustmentRule.next_business_day_on_holiday()
            ),
        )
    )
    occurrences = uc.list_occurrences(USER, date(2026, 10, 5), date(2026, 10, 25))
    assert source.asked == [USER]  # 展開 1 回で層は 1 度だけ引く
    return [o.date for o in occurrences]


def test_shift_skips_my_day_off() -> None:
    assert _dates(personal_counts=True) == [date(2026, 10, 5), date(2026, 10, 14), date(2026, 10, 19)]


def test_a_layer_that_does_not_count_does_not_move_the_occurrence() -> None:
    assert _dates(personal_counts=False) == [date(2026, 10, 5), date(2026, 10, 13), date(2026, 10, 19)]
