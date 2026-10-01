"""予定の時刻（移植元 docs/time-model.md §3・§4）。

- 単発: 開始の UTC 瞬間 ＋ 長さ（分）。終了は持たず ``開始 + 長さ`` で出す。
- 繰り返し: 先頭の回の UTC 瞬間（アンカー）＋ 長さ ＋ 規則。各回の瞬間はアンカーからの
  整数日の足し算で決まる（tz データベースを引き直さない）。
- 「終日」という概念は持たない。終日はローカル 00:00 開始 ＋ 1440 分の普通の予定。

瞬間はすべて naive な UTC で持つ（`src/shared/clock.utcnow()` と同じ形）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from src.domain.exceptions import ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.local_schedule_point import MINUTES_PER_DAY, to_naive_utc
from src.domain.value_objects.recurrence import RecurrenceRule


def _check_duration(duration_minutes: int) -> None:
    if duration_minutes <= 0:
        raise ValidationError("duration_minutes must be greater than zero")


@dataclass(frozen=True)
class SingleEventSchedule:
    start_utc: datetime
    duration_minutes: int

    def __post_init__(self) -> None:
        _check_duration(self.duration_minutes)
        object.__setattr__(self, "start_utc", to_naive_utc(self.start_utc))

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + timedelta(minutes=self.duration_minutes)


@dataclass(frozen=True)
class RecurringEventSchedule:
    anchor_utc: datetime
    duration_minutes: int
    recurrence_rule: RecurrenceRule

    def __post_init__(self) -> None:
        _check_duration(self.duration_minutes)
        object.__setattr__(self, "anchor_utc", to_naive_utc(self.anchor_utc))

    def with_recurrence_rule(self, rule: RecurrenceRule) -> RecurringEventSchedule:
        return RecurringEventSchedule(self.anchor_utc, self.duration_minutes, rule)


@dataclass(frozen=True)
class OccurrenceKey:
    """繰り返しの 1 回を指す鍵: 予定のタイムゾーンでの「候補日」＋「系列の開始時刻」。

    営業日シフトや移動の後でも、元の候補日で指す（移植元の ``OccurrenceLocalKey``）。
    """

    date: date
    time: time | None = None


@dataclass(frozen=True)
class EventOccurrence:
    """展開した 1 回。日付・時刻は予定のタイムゾーンの壁時計（表示用に投影したものは閲覧者の）。

    ``series_key`` は繰り返しの元の鍵（単発は表示用に投影したときに埋まる）。
    移動・切り出し・飛ばす操作はこの鍵で回を指す。
    """

    event_id: int | None
    date: date
    start_time: time
    duration_minutes: int
    title: str
    location: str | None = None
    is_moved: bool = False
    is_overridden: bool = False
    series_key: OccurrenceKey | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None

    @property
    def start_minute_of_day(self) -> int:
        return self.start_time.hour * 60 + self.start_time.minute

    @property
    def end_minute_from_start_day(self) -> int:
        """開始日の 0:00 から数えた終了（排他）の分。1440 を超えうる。"""
        return self.start_minute_of_day + self.duration_minutes

    @property
    def crosses_midnight(self) -> bool:
        return self.end_minute_from_start_day > MINUTES_PER_DAY

    @property
    def is_all_day(self) -> bool:
        """00:00 開始 ＋ 24 時間。画面の「終日」トグルはここから導く。"""
        return self.start_minute_of_day == 0 and self.duration_minutes == MINUTES_PER_DAY


__all__ = [
    "EventOccurrence",
    "OccurrenceKey",
    "RecurringEventSchedule",
    "SingleEventSchedule",
]
