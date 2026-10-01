"""予定の通知の設定（移植元 NolumiaScheduler の ``EventAlarm``、ADR-0021）。

基準は **回の開始時刻**（長さ・終了の変更の影響を受けない。移植元 docs/time-model.md §10-1・§11）。
15 分前・5 分前・1 分前・開始時刻（0 分前）のうち、入っているものごとに 1 回ずつ知らせる。

予定が通知を持たない（``CalendarEvent.alarm is None``）のと ``is_enabled=False`` は、どちらも
「知らせない」。後者は、どの時刻を選んでいたかを残したまま止めておく形（移植元と同じ）。
"""

from __future__ import annotations

from dataclasses import dataclass

ALARM_OFFSETS_MINUTES: tuple[int, ...] = (15, 5, 1, 0)
"""開始の何分前に知らせうるか（長い順）。0 は開始時刻ちょうど。移植元 ``AlarmScheduleCalculator.Offsets``。"""


@dataclass(frozen=True)
class EventAlarm:
    is_enabled: bool
    notify_15_min: bool
    notify_5_min: bool
    notify_1_min: bool
    notify_at_start: bool = True

    @classmethod
    def default(cls) -> EventAlarm:
        """新しい予定の既定（移植元 ``EventAlarm.Default``: 4 つとも入り）。"""
        return cls(True, True, True, True, True)

    def is_offset_enabled(self, minutes_before: int) -> bool:
        """``minutes_before``（``ALARM_OFFSETS_MINUTES`` のどれか）を選んでいるか。止めてあっても見る。"""
        if minutes_before == 15:
            return self.notify_15_min
        if minutes_before == 5:
            return self.notify_5_min
        if minutes_before == 1:
            return self.notify_1_min
        if minutes_before == 0:
            return self.notify_at_start
        return False

    def minutes_before(self) -> tuple[int, ...]:
        """実際に知らせる「開始の何分前」（長い順）。止めてあれば空。"""
        if not self.is_enabled:
            return ()
        return tuple(m for m in ALARM_OFFSETS_MINUTES if self.is_offset_enabled(m))


__all__ = ["ALARM_OFFSETS_MINUTES", "EventAlarm"]
