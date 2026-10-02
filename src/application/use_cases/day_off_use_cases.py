"""休みの層の日付と営業日の判定のユースケース（task #191 の 2 本目、ADR-0029）。

- 期間の休みの理由（画面の塗り・印・知らせ用）: 曜日の休み ＋ 日付の一覧の層の日
- 日付の一覧の層へ日を足す・消す・日本の祝日を年ごとに入れる（暦から出す。外へは取りに行かない）
- 予定の展開へ渡す層（``DayOffLayersSource`` の実装）

他人の層は「無い」= 404。予定のカレンダー・営業日の層に日付は足せない（422）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.calendar import Calendar, CalendarKind
from src.domain.entities.day_off import NAME_MAX_LENGTH, DayOff
from src.domain.exceptions import ValidationError
from src.domain.repositories.calendar_repository import CalendarRepository, DayOffRepository
from src.domain.services.day_off_layers import DayOffLayers, DayOffMark
from src.domain.services.default_calendar import ensure_day_off_layers
from src.domain.services.japanese_national_holidays import japanese_national_holidays
from src.shared.clock import utcnow

MAX_PERIOD_DAYS = 800
"""休みの理由を一度に引ける日数の上限（ガントの 2 年ぶんほど）。"""


class DayOffUseCases:
    def __init__(
        self,
        calendars: CalendarRepository,
        days_off: DayOffRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._calendars = calendars
        self._days_off = days_off
        self._uow = unit_of_work
        self._now = now

    # ── 判定 ────────────────────────────────────────────────────────────

    def layers_for(self, user_id: int, from_date: date | None = None, to_date: date | None = None) -> DayOffLayers:
        """その利用者の休みの層（日付は ``from_date``〜``to_date``。省けば全部）。"""
        calendars = self._calendars.find_all(user_id)
        layer_ids = [c.id for c in calendars if c.kind == CalendarKind.DAYS_OFF and c.id is not None]
        return DayOffLayers.of(calendars, self._days_off.find(layer_ids, from_date, to_date))

    def marks(self, user_id: int, from_date: date, to_date: date) -> list[DayOffMark]:
        """期間の休みの理由（日付の順）。数えない層の日も出す（画面は塗るが営業日の数には入れない）。"""
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        if (to_date - from_date) > timedelta(days=MAX_PERIOD_DAYS):
            raise ValidationError(f"the period must be {MAX_PERIOD_DAYS} days or shorter")
        self._ensure_layers(user_id)
        return self.layers_for(user_id, from_date, to_date).marks_between(from_date, to_date)

    # ── 日付の一覧の層 ──────────────────────────────────────────────────

    def list_days(
        self, calendar_id: int, user_id: int, from_date: date | None = None, to_date: date | None = None
    ) -> list[DayOff]:
        layer = self._owned_layer(calendar_id, user_id)
        assert layer.id is not None
        return self._days_off.find([layer.id], from_date, to_date)

    def add_day(self, calendar_id: int, user_id: int, day: date, name: str | None) -> list[DayOff]:
        """1 日足す（同じ日がすでにあれば何もしない）。その層の同じ年の日を返す。"""
        layer = self._owned_layer(calendar_id, user_id)
        assert layer.id is not None
        self._days_off.add(DayOff(layer.id, day, _day_name(name)))
        self._uow.commit()
        return self._year_of(layer.id, day.year)

    def remove_day(self, calendar_id: int, user_id: int, day: date) -> list[DayOff]:
        layer = self._owned_layer(calendar_id, user_id)
        assert layer.id is not None
        self._days_off.remove(layer.id, day)
        self._uow.commit()
        return self._year_of(layer.id, day.year)

    def import_japanese_holidays(self, calendar_id: int, user_id: int, year: int) -> list[DayOff]:
        """その年の日本の祝日・振替休日・国民の休日を足す（すでにある日はそのまま）。"""
        layer = self._owned_layer(calendar_id, user_id)
        assert layer.id is not None
        for holiday in japanese_national_holidays(year):
            self._days_off.add(DayOff(layer.id, holiday.date, holiday.name))
        self._uow.commit()
        return self._year_of(layer.id, year)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _ensure_layers(self, user_id: int) -> None:
        if ensure_day_off_layers(self._calendars, user_id, self._now()):
            self._uow.commit()

    def _year_of(self, calendar_id: int, year: int) -> list[DayOff]:
        return self._days_off.find([calendar_id], date(year, 1, 1), date(year, 12, 31))

    def _owned_layer(self, calendar_id: int, user_id: int) -> Calendar:
        calendar = owned_by(
            self._calendars.find_by_id(calendar_id), user_id,
            resource="Calendar", resource_id=calendar_id,
        )
        if calendar.kind != CalendarKind.DAYS_OFF:
            raise ValidationError("days can only be added to a days-off calendar")
        return calendar


def _day_name(name: str | None) -> str | None:
    if name is None or not name.strip():
        return None
    name = name.strip()
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a day-off name must be at most {NAME_MAX_LENGTH} characters")
    return name


__all__ = ["DayOffUseCases"]
