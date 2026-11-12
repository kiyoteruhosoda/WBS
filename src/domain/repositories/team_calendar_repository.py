from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date

from src.domain.entities.team_day_off import MemberDayOff, TeamDayOff, TeamExtraWorkday
from src.domain.value_objects.recurrence import Weekday


class TeamCalendarRepository(ABC):
    """Working weekdays (per root project), days off (on any project) and each person's leave (ADR-0058 decision 2, ADR-0059)."""

    @abstractmethod
    def workdays(self, project_id: int) -> frozenset[Weekday] | None:
        """The root's working weekdays. None if not set (Mon–Fri)."""

    @abstractmethod
    def workdays_by_project(self, project_ids: Iterable[int]) -> dict[int, frozenset[Weekday]]:
        """Only roots that have it set."""

    @abstractmethod
    def set_workdays(self, project_id: int, workdays: frozenset[Weekday]) -> None: ...

    @abstractmethod
    def team_days_off(
        self, project_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[TeamDayOff]:
        """In date order."""

    @abstractmethod
    def add_team_day_off(self, day_off: TeamDayOff) -> None:
        """If the same day exists, overwrite its name."""

    @abstractmethod
    def remove_team_day_off(self, project_id: int, day: date) -> None: ...

    @abstractmethod
    def extra_workdays(
        self, project_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[TeamExtraWorkday]:
        """Days worked on a non-working weekday (ADR-0060). In date order."""

    @abstractmethod
    def add_extra_workday(self, workday: TeamExtraWorkday) -> None:
        """If the same day exists, overwrite its name."""

    @abstractmethod
    def remove_extra_workday(self, project_id: int, day: date) -> None: ...

    @abstractmethod
    def forget_workdays(self, project_id: int) -> None:
        """Delete the weekdays when it stops being a root (days off remain as that project's own days off)."""

    @abstractmethod
    def member_days_off(
        self, user_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[MemberDayOff]:
        """In date order."""

    @abstractmethod
    def add_member_day_off(self, day_off: MemberDayOff) -> None:
        """If the same day exists, overwrite the leave ratio and working hours."""

    @abstractmethod
    def remove_member_day_off(self, user_id: int, day: date) -> None: ...
