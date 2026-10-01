"""営業日カレンダーのユースケース（移植元 ``BusinessCalendarApplicationService``）。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime

from src.application.dto.business_calendar_dto import (
    CreateBusinessCalendarCommand,
    UpdateBusinessCalendarCommand,
)
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.exceptions import ValidationError
from src.domain.repositories.business_calendar_repository import BusinessCalendarRepository
from src.domain.services.japanese_national_holidays import japanese_national_holidays
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow


class BusinessCalendarUseCases:
    def __init__(
        self,
        calendars: BusinessCalendarRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._calendars = calendars
        self._uow = unit_of_work
        self._now = now

    def list_calendars(self, user_id: int) -> list[BusinessCalendar]:
        return self._calendars.find_all(user_id)

    def get_calendar(self, calendar_id: int, user_id: int) -> BusinessCalendar:
        return self._owned(calendar_id, user_id)

    def create_calendar(self, cmd: CreateBusinessCalendarCommand) -> BusinessCalendar:
        now = self._now()
        calendar = BusinessCalendar(
            id=None,
            user_id=cmd.user_id,
            name=cmd.name,
            time_zone=TimeZoneId(cmd.time_zone),
            workdays=frozenset(cmd.workdays),
            shift_on_holidays_only=cmd.shift_on_holidays_only,
            is_enabled=cmd.is_enabled,
            created_at=now,
            updated_at=now,
        )
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def update_calendar(self, cmd: UpdateBusinessCalendarCommand) -> BusinessCalendar:
        """名前・営業日・シフトの仕方・有効を置き換える（祝日は残す）。"""
        calendar = self._owned(cmd.calendar_id, cmd.user_id)
        calendar.update(
            cmd.name, cmd.workdays, cmd.shift_on_holidays_only, cmd.is_enabled, self._now()
        )
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def add_holiday(
        self, calendar_id: int, user_id: int, day: date, name: str | None = None
    ) -> BusinessCalendar:
        """祝日を足す。同じ日がすでにあれば何もしない。"""
        calendar = self._owned(calendar_id, user_id)
        calendar.add_holiday(Holiday(day, name), self._now())
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def add_holidays(
        self, calendar_id: int, user_id: int, holidays: Iterable[Holiday]
    ) -> BusinessCalendar:
        """祝日をまとめて足す（年ごとの一括登録）。すでにある日は名前も変えずに残す。"""
        calendar = self._owned(calendar_id, user_id)
        now = self._now()
        for holiday in holidays:
            calendar.add_holiday(holiday, now)
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def import_japanese_national_holidays(
        self, calendar_id: int, user_id: int, year: int
    ) -> BusinessCalendar:
        """その年の日本の祝日・振替休日・国民の休日を足す（暦から出す。外へは取りに行かない）。"""
        return self.add_holidays(calendar_id, user_id, japanese_national_holidays(year))

    def list_holidays(self, user_id: int, from_date: date, to_date: date) -> list[Holiday]:
        """有効な営業日カレンダーの祝日を期間で集める（画面の強調表示用）。

        同じ日が複数のカレンダーにあれば、先に作ったカレンダーの名前を使う。
        """
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        found: dict[date, Holiday] = {}
        for calendar in self._calendars.find_all(user_id):
            if not calendar.is_enabled:
                continue
            for holiday in calendar.holidays:
                if from_date <= holiday.date <= to_date:
                    found.setdefault(holiday.date, holiday)
        return [found[day] for day in sorted(found)]

    def remove_holiday(self, calendar_id: int, user_id: int, day: date) -> BusinessCalendar:
        calendar = self._owned(calendar_id, user_id)
        calendar.remove_holiday(day, self._now())
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def delete_calendar(self, calendar_id: int, user_id: int) -> None:
        """消す。参照していた繰り返しは、以後シフトせずに名目の日に出る（移植元と同じ）。"""
        self._owned(calendar_id, user_id)
        self._calendars.delete(calendar_id)
        self._uow.commit()

    def _owned(self, calendar_id: int, user_id: int) -> BusinessCalendar:
        return owned_by(
            self._calendars.find_by_id(calendar_id), user_id,
            resource="BusinessCalendar", resource_id=calendar_id,
        )


__all__ = ["BusinessCalendarUseCases"]
