"""PC を使っていた時間（WinTrack → wbstimer、task #397 / ADR-0049）。

WinTrack はその日（送り手のタイムゾーンでの日付）に PC を使っていた区間を送り、**丸ごと置き換える**
（送り直しても同じ。``[]`` で全部消える）。wbstimer は開始・終了を押したときに読み、
「PC で既に作業していたか」を聞く。打刻・実績・締めには使わないので、確定済みの締めの期間の日でも受ける。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from src.application.dto.pc_activity_dto import PcActivityInPeriod
from src.application.ports.unit_of_work import UnitOfWork
from src.domain.entities.pc_activity import PcActivityDay, PcActivitySpan
from src.domain.exceptions import ValidationError
from src.domain.repositories.pc_activity_repository import PcActivityRepository
from src.domain.value_objects.half_month_period import local_midnight_utc
from src.domain.value_objects.press_time import CLOCK_SKEW_ALLOWANCE, MAX_PRESS_AGE
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow

MAX_SPANS_PER_DAY = 500
"""1 日に受け取る区間の上限（5 分未満の切れ目はつなぐので、1 日に 288 を超えない）。"""

RETENTION = timedelta(days=35)
"""これより前に終わった日は、書くときに消す（wbstimer が読むのは今日だけ）。"""


class PcActivityUseCases:
    def __init__(
        self,
        repository: PcActivityRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repository = repository
        self._uow = unit_of_work
        self._now = now

    def replace_day(
        self,
        user_id: int,
        day: date,
        time_zone: str,
        spans: list[tuple[datetime, datetime]],
    ) -> PcActivityDay:
        """``day`` の区間を ``spans``（naive な UTC）で置き換える。

        - 区間はその日の中に収まり・重ならず・終わりが始まりより後（違えば ``ValidationError`` = 422）
        - 7 日より前・未来は打刻と同じ制限（未来は 60 秒まで「今」に寄せる）
        - 締めには関係しないので、確定済みの締めの期間の日でも受ける
        - ついでに 35 日より前に終わった日を消す
        """
        if len(spans) > MAX_SPANS_PER_DAY:
            raise ValidationError(f"too many spans (at most {MAX_SPANS_PER_DAY} a day)")
        now = self._now().replace(microsecond=0)
        zone = TimeZoneId(time_zone)
        day_start = local_midnight_utc(day, zone.zone)
        day_end = local_midnight_utc(day + timedelta(days=1), zone.zone)
        if day_end <= now - MAX_PRESS_AGE:
            raise ValidationError(
                f"the day is too far in the past (at most {MAX_PRESS_AGE.days} days ago)"
            )
        if day_start > now + CLOCK_SKEW_ALLOWANCE:
            raise ValidationError("the day must not be in the future")

        cleaned: list[tuple[datetime, datetime]] = []
        for started_at, ended_at in spans:
            started_at, ended_at = (
                started_at.replace(microsecond=0),
                ended_at.replace(microsecond=0),
            )
            if ended_at <= started_at:
                raise ValidationError("ended_at must be after started_at")
            if started_at < day_start or ended_at > day_end:
                raise ValidationError("a span must be inside the day")
            if started_at < now - MAX_PRESS_AGE:
                raise ValidationError(
                    f"a span is too far in the past (at most {MAX_PRESS_AGE.days} days ago)"
                )
            if ended_at > now + CLOCK_SKEW_ALLOWANCE:
                raise ValidationError("a span must not be in the future")
            started_at, ended_at = min(started_at, now), min(ended_at, now)
            if ended_at <= started_at:
                raise ValidationError("ended_at must be after started_at")
            cleaned.append((started_at, ended_at))
        cleaned.sort()
        for (_, previous_end), (next_start, _) in zip(cleaned, cleaned[1:], strict=False):
            if next_start < previous_end:
                raise ValidationError("spans must not overlap")

        self._repository.delete_days_ended_before(user_id, now - RETENTION)
        saved = self._repository.replace_day(
            PcActivityDay(
                id=None,
                user_id=user_id,
                local_date=day,
                time_zone=str(zone),
                starts_at=day_start,
                ends_at=day_end,
                updated_at=now,
                spans=[
                    PcActivitySpan(id=None, user_id=user_id, started_at=s, ended_at=e)
                    for s, e in cleaned
                ],
            )
        )
        self._uow.commit()
        return saved

    def list_in_period(self, user_id: int, start: datetime, end: datetime) -> PcActivityInPeriod:
        """``[start, end)``（naive な UTC）に掛かる区間を始まりの順に、範囲の日の最後に受けた時刻と。"""
        if end <= start:
            raise ValidationError("end must be after start")
        return PcActivityInPeriod(
            spans=self._repository.find_overlapping(user_id, start, end),
            updated_at=self._repository.last_updated_at(user_id, start, end),
        )
