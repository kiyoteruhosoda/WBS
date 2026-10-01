"""営業日カレンダーのユースケース（移植元 CoreTests/BusinessCalendarServiceTests.cs のうち画面に依らない分）。"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.application.dto.business_calendar_dto import (
    CreateBusinessCalendarCommand,
    UpdateBusinessCalendarCommand,
)
from src.application.use_cases.business_calendar_use_cases import BusinessCalendarUseCases
from src.domain.entities.business_calendar import Holiday
from src.domain.exceptions import NotFoundError
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday
from tests.unit.application.scheduling.fakes import (
    FakeClock,
    InMemoryBusinessCalendarRepository,
    RecordingUnitOfWork,
)

USER = 1
OTHER_USER = 2


@pytest.fixture
def uc() -> BusinessCalendarUseCases:
    return BusinessCalendarUseCases(
        InMemoryBusinessCalendarRepository(), RecordingUnitOfWork(), now=FakeClock(datetime(2026, 5, 1))
    )


def _create(uc: BusinessCalendarUseCases, **kwargs) -> int:
    calendar = uc.create_calendar(CreateBusinessCalendarCommand(USER, "JP", "Asia/Tokyo", **kwargs))
    assert calendar.id is not None
    return calendar.id


def test_create_with_no_holidays(uc: BusinessCalendarUseCases) -> None:
    calendar = uc.get_calendar(_create(uc), USER)
    assert calendar.holidays == []
    assert calendar.workdays == WEEKDAYS_MON_TO_FRI
    assert not calendar.shift_on_holidays_only
    assert calendar.is_enabled


def test_add_holiday_with_and_without_name(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    uc.add_holiday(calendar_id, USER, date(2026, 1, 1), "元日")
    uc.add_holiday(calendar_id, USER, date(2026, 1, 12))
    assert uc.get_calendar(calendar_id, USER).holidays == [
        Holiday(date(2026, 1, 1), "元日"), Holiday(date(2026, 1, 12), None)
    ]


def test_add_duplicate_holiday_is_ignored(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    uc.add_holiday(calendar_id, USER, date(2026, 1, 1), "元日")
    uc.add_holiday(calendar_id, USER, date(2026, 1, 1), "別名")
    assert uc.get_calendar(calendar_id, USER).holidays == [Holiday(date(2026, 1, 1), "元日")]


def test_update_preserves_existing_holidays(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    uc.add_holiday(calendar_id, USER, date(2026, 1, 1), "元日")
    uc.update_calendar(
        UpdateBusinessCalendarCommand(
            calendar_id, USER, "Renamed", frozenset({Weekday.MONDAY}), shift_on_holidays_only=True,
            is_enabled=False,
        )
    )
    calendar = uc.get_calendar(calendar_id, USER)
    assert calendar.name == "Renamed"
    assert calendar.workdays == frozenset({Weekday.MONDAY})
    assert calendar.shift_on_holidays_only
    assert not calendar.is_enabled
    assert calendar.holidays == [Holiday(date(2026, 1, 1), "元日")]


def test_remove_holiday_removes_the_right_date(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    uc.add_holiday(calendar_id, USER, date(2026, 1, 1), "元日")
    uc.add_holiday(calendar_id, USER, date(2026, 2, 11), "建国記念の日")
    uc.remove_holiday(calendar_id, USER, date(2026, 1, 1))
    assert uc.get_calendar(calendar_id, USER).holidays == [Holiday(date(2026, 2, 11), "建国記念の日")]


def test_create_with_shift_on_holidays_only(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc, shift_on_holidays_only=True)
    assert uc.get_calendar(calendar_id, USER).shift_on_holidays_only


def test_other_users_calendar_is_not_found(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    with pytest.raises(NotFoundError):
        uc.get_calendar(calendar_id, OTHER_USER)
    with pytest.raises(NotFoundError):
        uc.add_holiday(calendar_id, OTHER_USER, date(2026, 1, 1))
    with pytest.raises(NotFoundError):
        uc.delete_calendar(calendar_id, OTHER_USER)
    assert uc.list_calendars(OTHER_USER) == []
    assert [c.id for c in uc.list_calendars(USER)] == [calendar_id]


def test_delete_calendar(uc: BusinessCalendarUseCases) -> None:
    calendar_id = _create(uc)
    uc.delete_calendar(calendar_id, USER)
    assert uc.list_calendars(USER) == []
