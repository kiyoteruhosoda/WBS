"""休み（WinTrack、task #392 / ADR-0048）。

WinTrack は PC で決めた休み（作業と作業の間で手が止まった時間・「休みにする」にした作業）を日ごとに送る。
その日（送り手のタイムゾーンでの日付）の**自動の休みを丸ごと置き換える**（送り直しても同じ。``[]`` で全部消える）。
休みは打刻を切り抜かない。実績の長さを出すところで、打刻と重なる休みの時間を引く（``allocate_by_local_day``）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from src.application.ports.unit_of_work import UnitOfWork
from src.domain.entities.work_break import WorkBreak, WorkBreakSource
from src.domain.exceptions import ConflictError, ValidationError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.work_break_repository import WorkBreakRepository
from src.domain.value_objects.half_month_period import local_midnight_utc
from src.domain.value_objects.press_time import CLOCK_SKEW_ALLOWANCE, MAX_PRESS_AGE
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow

MAX_BREAKS_PER_DAY = 200
"""1 日に受け取る休みの上限。"""


class WorkBreakUseCases:
    def __init__(
        self,
        breaks: WorkBreakRepository,
        closing_periods: ClosingPeriodRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._breaks = breaks
        self._closing_periods = closing_periods
        self._uow = unit_of_work
        self._now = now

    def replace_automatic(
        self,
        user_id: int,
        day: date,
        time_zone: str,
        spans: list[tuple[datetime, datetime]],
    ) -> list[WorkBreak]:
        """``day`` の自動の休みを ``spans``（naive な UTC）で置き換える。

        - 区間はその日の中に収まり・重ならず・終わりが始まりより後（違えば ``ValidationError`` = 422）
        - 7 日より前・未来は打刻と同じ制限（未来は 60 秒まで「今」に寄せる）
        - 確定済みの締めの期間に掛かる日は ``ConflictError``（409、``closed``）。置き換えない
        """
        if len(spans) > MAX_BREAKS_PER_DAY:
            raise ValidationError(f"too many breaks (at most {MAX_BREAKS_PER_DAY} a day)")
        now = self._now()
        zone = TimeZoneId(time_zone)
        day_start = local_midnight_utc(day, zone.zone)
        day_end = local_midnight_utc(day + timedelta(days=1), zone.zone)
        if day_end <= now - MAX_PRESS_AGE:
            raise ValidationError(f"the day is too far in the past (at most {MAX_PRESS_AGE.days} days ago)")
        if day_start > now + CLOCK_SKEW_ALLOWANCE:
            raise ValidationError("the day must not be in the future")

        cleaned: list[tuple[datetime, datetime]] = []
        for started_at, ended_at in spans:
            started_at, ended_at = started_at.replace(microsecond=0), ended_at.replace(microsecond=0)
            if ended_at <= started_at:
                raise ValidationError("ended_at must be after started_at")
            if started_at < day_start or ended_at > day_end:
                raise ValidationError("a break must be inside the day")
            if started_at < now - MAX_PRESS_AGE:
                raise ValidationError(f"a break is too far in the past (at most {MAX_PRESS_AGE.days} days ago)")
            if ended_at > now + CLOCK_SKEW_ALLOWANCE:
                raise ValidationError("a break must not be in the future")
            started_at, ended_at = min(started_at, now), min(ended_at, now)
            if ended_at <= started_at:
                raise ValidationError("ended_at must be after started_at")
            cleaned.append((started_at, ended_at))
        cleaned.sort()
        for (_, previous_end), (next_start, _) in zip(cleaned, cleaned[1:], strict=False):
            if next_start < previous_end:
                raise ValidationError("breaks must not overlap")

        if self._closing_periods.find_overlapping(user_id, day_start, day_end):
            raise ConflictError("closed")

        saved = self._breaks.replace(
            user_id,
            WorkBreakSource.AUTO,
            day_start,
            day_end,
            [WorkBreak(id=None, user_id=user_id, started_at=s, ended_at=e) for s, e in cleaned],
        )
        self._uow.commit()
        return saved

    def list_in_period(self, user_id: int, start: datetime, end: datetime) -> list[WorkBreak]:
        """``[start, end)``（naive な UTC）に掛かる休みを始まりの順に。"""
        if end <= start:
            raise ValidationError("end must be after start")
        return self._breaks.find_overlapping(user_id, start, end)
