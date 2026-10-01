"""予定・営業日カレンダーの表の実装（ADR-0009）。

- 例外・移動・祝日は子表で、読み直すと同じ集約に戻る
- 期間の列（``span_start_day`` / ``span_end_day``）で粗く絞れる
- 楽観ロック: 同じ予定を 2 つの接続で読み、片方が先に確定したら、もう片方の保存は ``ConflictError``
- ``save`` は確定しない（確定はユースケースの ``UnitOfWork``）
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, datetime, time

import pytest
from sqlalchemy.orm import Session

from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.entities.calendar_event import CalendarEvent, EventMove
from src.domain.exceptions import ConflictError
from src.domain.value_objects.event_schedule import (
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.recurrence import (
    NO_END_DATE,
    WEEKDAYS_MON_TO_FRI,
    AdjustmentRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
)
from src.domain.value_objects.time_zone import TimeZoneId
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.session import get_session_factory
from src.infrastructure.repositories.business_calendar_repository import (
    SqlAlchemyBusinessCalendarRepository,
)
from src.infrastructure.repositories.calendar_event_repository import (
    SqlAlchemyCalendarEventRepository,
)

TOKYO = TimeZoneId("Asia/Tokyo")
NOW = datetime(2026, 10, 1, 0, 0)
MONDAY_9_JST = datetime(2026, 10, 5, 0, 0)  # 2026-10-05 09:00 JST


@pytest.fixture
def sessions(client) -> Iterator[Callable[[], Session]]:
    opened: list[Session] = []

    def open_session() -> Session:
        session = get_session_factory()()
        opened.append(session)
        return session

    yield open_session
    for session in opened:
        session.close()


def _weekly_event(calendar_id: int | None = None) -> CalendarEvent:
    rule = RecurrenceRule(
        RecurrenceType.WEEKLY, 1, NO_END_DATE,
        weekly=WeeklyRule((Weekday.MONDAY, Weekday.WEDNESDAY)),
        adjustment=AdjustmentRule.next_business_day_on_holiday(calendar_id) if calendar_id else None,
    )
    return CalendarEvent.create_recurring(
        user_id=SINGLE_USER_ID, title="定例", time_zone=TOKYO,
        schedule=RecurringEventSchedule(MONDAY_9_JST, 60, rule), created_at=NOW,
    )


def _single_event(start: datetime) -> CalendarEvent:
    return CalendarEvent.create_single(
        user_id=SINGLE_USER_ID, title="単発", time_zone=TOKYO,
        schedule=SingleEventSchedule(start, 30), created_at=NOW,
    )


def test_recurring_event_round_trips_with_exceptions_and_moves(sessions) -> None:
    writer = sessions()
    repo = SqlAlchemyCalendarEventRepository(writer)
    event = repo.save(_weekly_event())
    event.skip_occurrence(OccurrenceKey(date(2026, 10, 7), time(9, 0)), NOW)
    event.move_occurrence(
        OccurrenceKey(date(2026, 10, 12), time(9, 0)),
        new_date=date(2026, 10, 13), new_start_time=time(11, 0), duration_minutes=45,
        title="火曜へ", location=None, updated_at=NOW,
    )
    repo.save(event)
    writer.commit()

    loaded = SqlAlchemyCalendarEventRepository(sessions()).find_by_id(event.id)
    assert loaded is not None
    assert loaded.recurring_schedule == event.recurring_schedule
    assert loaded.exceptions == event.exceptions
    assert loaded.moves == [
        EventMove(
            OccurrenceKey(date(2026, 10, 12), time(9, 0)),
            date(2026, 10, 13), time(11, 0), 45, "火曜へ", None,
        )
    ]
    assert loaded.version == 3


def test_replacing_the_same_occurrence_key_does_not_trip_the_unique_constraint(sessions) -> None:
    session = sessions()
    repo = SqlAlchemyCalendarEventRepository(session)
    event = repo.save(_weekly_event())
    key = OccurrenceKey(date(2026, 10, 7), time(9, 0))
    event.skip_occurrence(key, NOW)
    repo.save(event)
    # 同じ回をもう一度飛ばす（消して入れ直す）
    event.skip_occurrence(key, NOW)
    repo.save(event)
    session.commit()
    assert len(repo.find_by_id(event.id).exceptions) == 1


def test_find_by_period_uses_the_span_columns(sessions) -> None:
    session = sessions()
    repo = SqlAlchemyCalendarEventRepository(session)
    near = repo.save(_single_event(datetime(2026, 10, 5, 0, 0)))
    far = repo.save(_single_event(datetime(2027, 6, 1, 0, 0)))
    session.commit()

    found = {e.id for e in repo.find_by_period(SINGLE_USER_ID, date(2026, 10, 1), date(2026, 10, 31))}
    assert near.id in found
    assert far.id not in found
    assert repo.find_by_period(SINGLE_USER_ID + 999, date(2026, 10, 1), date(2026, 10, 31)) == []


def test_save_does_not_commit(sessions) -> None:
    session = sessions()
    repo = SqlAlchemyCalendarEventRepository(session)
    event = repo.save(_single_event(MONDAY_9_JST))
    session.rollback()
    assert SqlAlchemyCalendarEventRepository(sessions()).find_by_id(event.id) is None


def test_a_save_based_on_a_stale_read_is_a_conflict(sessions) -> None:
    setup = sessions()
    event_id = SqlAlchemyCalendarEventRepository(setup).save(_weekly_event()).id
    setup.commit()

    first_session, second_session = sessions(), sessions()
    first = SqlAlchemyCalendarEventRepository(first_session)
    second = SqlAlchemyCalendarEventRepository(second_session)
    mine = first.find_by_id(event_id)
    theirs = second.find_by_id(event_id)

    mine.change_details(title="先", location=None, description=None, task_id=None, updated_at=NOW)
    first.save(mine)
    first_session.commit()

    theirs.change_details(title="後", location=None, description=None, task_id=None, updated_at=NOW)
    from src.infrastructure.database.models import CalendarEventModel  # 一時の診断

    fresh = sessions()
    observed = (
        fresh.get(CalendarEventModel, event_id).version,
        second_session.get(CalendarEventModel, event_id).version,
        theirs.version,
        first_session is second_session,
        first_session.get_bind() is second_session.get_bind(),
        str(first_session.get_bind().pool.__class__.__name__),
    )
    assert observed == (2, 1, 2, False, True, "QueuePool")
    with pytest.raises(ConflictError):
        second.save(theirs)
    second_session.rollback()

    assert SqlAlchemyCalendarEventRepository(sessions()).find_by_id(event_id).title == "先"


def test_a_delete_based_on_a_stale_read_is_a_conflict(sessions) -> None:
    setup = sessions()
    event_id = SqlAlchemyCalendarEventRepository(setup).save(_single_event(MONDAY_9_JST)).id
    setup.commit()

    first_session, second_session = sessions(), sessions()
    first = SqlAlchemyCalendarEventRepository(first_session)
    second = SqlAlchemyCalendarEventRepository(second_session)
    mine = first.find_by_id(event_id)
    second.find_by_id(event_id)

    mine.change_details(title="直した", location=None, description=None, task_id=None, updated_at=NOW)
    first.save(mine)
    first_session.commit()

    with pytest.raises(ConflictError):
        second.delete(event_id)


def test_business_calendar_round_trips_with_holidays(sessions) -> None:
    session = sessions()
    repo = SqlAlchemyBusinessCalendarRepository(session)
    calendar = repo.save(
        BusinessCalendar(
            id=None, user_id=SINGLE_USER_ID, name="日本", time_zone=TOKYO,
            workdays=WEEKDAYS_MON_TO_FRI, created_at=NOW, updated_at=NOW,
        )
    )
    calendar.add_holiday(Holiday(date(2026, 11, 3), "文化の日"), NOW)
    calendar.add_holiday(Holiday(date(2026, 1, 1), "元日"), NOW)
    repo.save(calendar)
    # 同じ日を消して入れ直しても一意制約に当たらない
    calendar.remove_holiday(date(2026, 1, 1), NOW)
    calendar.add_holiday(Holiday(date(2026, 1, 1), "元日"), NOW)
    repo.save(calendar)
    session.commit()

    loaded = SqlAlchemyBusinessCalendarRepository(sessions()).find_by_id(calendar.id)
    assert loaded.workdays == WEEKDAYS_MON_TO_FRI
    assert [(h.date, h.name) for h in loaded.holidays] == [
        (date(2026, 1, 1), "元日"),
        (date(2026, 11, 3), "文化の日"),
    ]
    assert SqlAlchemyBusinessCalendarRepository(sessions()).find_all(SINGLE_USER_ID + 999) == []
