"""予定の通知の設定（移植元 ``EventAlarm`` / ``AlarmScheduleCalculator.IsOffsetEnabled``、ADR-0021）。"""

from __future__ import annotations

from src.domain.value_objects.event_alarm import ALARM_OFFSETS_MINUTES, EventAlarm


def test_the_default_turns_every_offset_on() -> None:
    assert EventAlarm.default() == EventAlarm(True, True, True, True, True)
    assert EventAlarm.default().minutes_before() == (15, 5, 1, 0)


def test_offsets_are_longest_first_and_zero_is_the_start() -> None:
    assert ALARM_OFFSETS_MINUTES == (15, 5, 1, 0)


def test_only_the_chosen_offsets_ring() -> None:
    alarm = EventAlarm(is_enabled=True, notify_15_min=False, notify_5_min=True,
                       notify_1_min=False, notify_at_start=True)
    assert alarm.minutes_before() == (5, 0)
    assert alarm.is_offset_enabled(5)
    assert not alarm.is_offset_enabled(15)
    assert not alarm.is_offset_enabled(30)  # 選べない時刻


def test_a_disabled_alarm_keeps_its_choices_but_does_not_ring() -> None:
    alarm = EventAlarm(False, True, True, True, True)
    assert alarm.minutes_before() == ()
    assert alarm.is_offset_enabled(15)
