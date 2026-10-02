"""インメモリのリポジトリと確定口（表ができるまでの試験用）。

保存・取り出しのたびに複製するので、``save`` を呼び忘れた変更は残らない
（実物の DB と同じく、取り出したものを書き換えただけでは保存されない）。
"""

from __future__ import annotations

import copy
from datetime import date

from src.domain.entities.business_calendar import BusinessCalendar
from src.domain.entities.calendar import Calendar
from src.domain.entities.calendar_event import CalendarEvent
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.entities.task import Task
from src.domain.repositories.business_calendar_repository import BusinessCalendarRepository
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.repositories.calendar_repository import (
    CalendarRepository,
    CalendarViewPresetRepository,
)


class InMemoryCalendarEventRepository(CalendarEventRepository):
    def __init__(self) -> None:
        self._rows: dict[int, CalendarEvent] = {}
        self._next_id = 1

    def find_by_id(self, event_id: int) -> CalendarEvent | None:
        found = self._rows.get(event_id)
        return copy.deepcopy(found) if found is not None else None

    def find_by_period(self, user_id: int, from_date: date, to_date: date) -> list[CalendarEvent]:
        return [
            copy.deepcopy(e) for e in self._rows.values()
            if e.user_id == user_id and e.overlaps_period(from_date, to_date)
        ]

    def save(self, event: CalendarEvent) -> CalendarEvent:
        if event.id is None:
            event.id = self._next_id
            self._next_id += 1
        self._rows[event.id] = copy.deepcopy(event)
        return copy.deepcopy(event)

    def delete(self, event_id: int) -> None:
        self._rows.pop(event_id, None)

    def reassign_calendar(self, user_id: int, from_calendar_id: int, to_calendar_id: int) -> int:
        moved = 0
        for event in self._rows.values():
            if event.user_id == user_id and event.calendar_id == from_calendar_id:
                event.calendar_id = to_calendar_id
                event.version += 1
                moved += 1
        return moved

    def all(self) -> list[CalendarEvent]:
        return [copy.deepcopy(e) for e in self._rows.values()]


class InMemoryBusinessCalendarRepository(BusinessCalendarRepository):
    def __init__(self) -> None:
        self._rows: dict[int, BusinessCalendar] = {}
        self._next_id = 1

    def find_by_id(self, calendar_id: int) -> BusinessCalendar | None:
        found = self._rows.get(calendar_id)
        return copy.deepcopy(found) if found is not None else None

    def find_all(self, user_id: int) -> list[BusinessCalendar]:
        return [copy.deepcopy(c) for c in self._rows.values() if c.user_id == user_id]

    def save(self, calendar: BusinessCalendar) -> BusinessCalendar:
        if calendar.id is None:
            calendar.id = self._next_id
            self._next_id += 1
        self._rows[calendar.id] = copy.deepcopy(calendar)
        return copy.deepcopy(calendar)

    def delete(self, calendar_id: int) -> None:
        self._rows.pop(calendar_id, None)


class InMemoryCalendarRepository(CalendarRepository):
    def __init__(self) -> None:
        self._rows: dict[int, Calendar] = {}
        self._next_id = 1

    def find_by_id(self, calendar_id: int) -> Calendar | None:
        found = self._rows.get(calendar_id)
        return copy.deepcopy(found) if found is not None else None

    def find_all(self, user_id: int) -> list[Calendar]:
        rows = [c for c in self._rows.values() if c.user_id == user_id]
        return [copy.deepcopy(c) for c in sorted(rows, key=lambda c: (c.sort_order, c.id or 0))]

    def save(self, calendar: Calendar) -> Calendar:
        if calendar.id is None:
            calendar.id = self._next_id
            self._next_id += 1
        self._rows[calendar.id] = copy.deepcopy(calendar)
        return copy.deepcopy(calendar)

    def delete(self, calendar_id: int) -> None:
        self._rows.pop(calendar_id, None)


class InMemoryCalendarViewPresetRepository(CalendarViewPresetRepository):
    def __init__(self) -> None:
        self._rows: dict[int, CalendarViewPreset] = {}
        self._next_id = 1

    def find_by_id(self, preset_id: int) -> CalendarViewPreset | None:
        found = self._rows.get(preset_id)
        return copy.deepcopy(found) if found is not None else None

    def find_all(self, user_id: int) -> list[CalendarViewPreset]:
        rows = [p for p in self._rows.values() if p.user_id == user_id]
        return [copy.deepcopy(p) for p in sorted(rows, key=lambda p: (p.sort_order, p.id or 0))]

    def save(self, preset: CalendarViewPreset) -> CalendarViewPreset:
        if preset.id is None:
            preset.id = self._next_id
            self._next_id += 1
        self._rows[preset.id] = copy.deepcopy(preset)
        return copy.deepcopy(preset)

    def delete(self, preset_id: int) -> None:
        self._rows.pop(preset_id, None)


class FakeTasks:
    """``OwnedTaskLookup``。``owners`` は task_id → user_id。"""

    def __init__(self, owners: dict[int, int] | None = None) -> None:
        self._owners = owners or {}

    def find_by_id_for_user(self, task_id: int, user_id: int) -> Task | None:
        if self._owners.get(task_id) != user_id:
            return None
        return Task(id=task_id, user_id=user_id, title=f"task {task_id}")


class RecordingUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeClock:
    """``now`` に渡す時計。試験の中でだけ進む（移植元 CoreTests/FakeClock.cs）。"""

    def __init__(self, now) -> None:
        self.current = now

    def __call__(self):
        return self.current
