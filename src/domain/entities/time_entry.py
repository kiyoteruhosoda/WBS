"""打刻（タイムトラッカーの 1 区間）。

打刻は**下書き**で、締め（task #161）で確定したものが ``work_logs`` になる（ADR-0008）。
時刻はすべて naive な UTC（``src.shared.clock.utcnow()`` と保存値の形）。

- ``ended_at`` が空の間は「走っている」。走っている打刻は 1 人 1 本（表の部分一意索引でも守る）
- 止め忘れはその場では直させない。長さが ``LONG_RUNNING_THRESHOLD`` を超えたら印を付けるだけ
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.exceptions import ValidationError
from src.domain.value_objects.time_entry_source import TimeEntrySource

LONG_RUNNING_THRESHOLD = timedelta(hours=12)
"""これを超えた打刻に「長すぎる（止め忘れかも）」の印を付ける。"""


@dataclass
class TimeEntry:
    id: int | None
    user_id: int
    started_at: datetime
    ended_at: datetime | None = None
    task_id: int | None = None
    memo: str | None = None
    source: TimeEntrySource = TimeEntrySource.TIMER
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def start(
        cls, *, user_id: int, at: datetime, task_id: int | None, memo: str | None = None
    ) -> TimeEntry:
        return cls(id=None, user_id=user_id, started_at=at, task_id=task_id, memo=memo)

    @property
    def is_running(self) -> bool:
        return self.ended_at is None

    def stop(self, at: datetime) -> None:
        """止める。走っていなければ何もしない（冪等）。

        端末の時計のずれなどで ``at`` が始まりより前になったときは、長さ 0 で止める
        （負の長さを作らない）。
        """
        if not self.is_running:
            return
        self.ended_at = max(at, self.started_at)

    def duration(self, now: datetime) -> timedelta:
        """長さ。走っている間は ``now`` までを数える。"""
        end = self.ended_at if self.ended_at is not None else now
        return max(end - self.started_at, timedelta(0))

    def is_long_running(self, now: datetime) -> bool:
        return self.duration(now) > LONG_RUNNING_THRESHOLD

    def reschedule(self, *, started_at: datetime, ended_at: datetime | None, now: datetime) -> None:
        """始まり・終わりを直す（締めの画面から）。

        - 終わりは始まりより後
        - 未来の時刻は入れない（走っている打刻の経過が負になる・まだ起きていない作業になる）
        - 止まっている打刻を走っている状態へ戻さない（1 人 1 本を崩しうるため。
          続きは Start で新しく始める）
        """
        if ended_at is None and not self.is_running:
            raise ValidationError("A stopped time entry cannot be made running again")
        if started_at > now:
            raise ValidationError("started_at must not be in the future")
        if ended_at is not None:
            if ended_at > now:
                raise ValidationError("ended_at must not be in the future")
            if ended_at <= started_at:
                raise ValidationError("ended_at must be after started_at")
        self.started_at = started_at
        self.ended_at = ended_at

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """``[start, end)`` に掛かるか。走っている打刻は終わりが無いものとして扱う。

        長さ 0 の打刻（始まり＝終わり）は、始まりが区間に入っていれば掛かるとみなす。
        区間のちょうど始まりで終わった打刻（前日の 23:00〜0:00）は掛からない。
        """
        if self.started_at >= end:
            return False
        return self.ended_at is None or self.ended_at > start or self.started_at >= start
