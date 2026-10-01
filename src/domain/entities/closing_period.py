"""確定した締めの期間（task #161 / ADR-0012）。

**行がある = 確定済み。** 開け直すと行ごと消える（その期間から作った ``work_logs`` も消える）。
期間は利用者のタイムゾーンの日付（``first_day``〜``last_day``）で、確定したときのタイムゾーンで
出した区切りの瞬間（``starts_at`` / ``ends_at``、naive な UTC の半開区間）を一緒に持つ。
打刻を書き換えさせないかどうかは、この**瞬間**で判定する（あとで利用者がタイムゾーンを
変えても、確定した範囲は動かない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.domain.value_objects.half_month_period import HalfMonthPeriod
from src.domain.value_objects.time_zone import TimeZoneId


@dataclass
class ClosingPeriod:
    id: int | None
    user_id: int
    first_day: date
    last_day: date
    time_zone: str
    starts_at: datetime
    ends_at: datetime
    closed_at: datetime

    @classmethod
    def close(
        cls, *, user_id: int, period: HalfMonthPeriod, time_zone: TimeZoneId, now: datetime
    ) -> ClosingPeriod:
        starts_at, ends_at = period.utc_window(time_zone.zone)
        return cls(
            id=None,
            user_id=user_id,
            first_day=period.first_day,
            last_day=period.last_day,
            time_zone=time_zone.name,
            starts_at=starts_at,
            ends_at=ends_at,
            closed_at=now,
        )

    @property
    def period(self) -> HalfMonthPeriod:
        return HalfMonthPeriod(self.first_day, self.last_day)
