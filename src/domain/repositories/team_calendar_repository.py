from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date

from src.domain.entities.team_day_off import MemberDayOff, TeamDayOff
from src.domain.value_objects.recurrence import Weekday


class TeamCalendarRepository(ABC):
    """チームの稼働する曜日・休日（根のプロジェクトごと）と、各人の休み（ADR-0058 決定 2）。"""

    @abstractmethod
    def workdays(self, project_id: int) -> frozenset[Weekday] | None:
        """根の稼働する曜日。入れていなければ None（月〜金）。"""

    @abstractmethod
    def workdays_by_project(self, project_ids: Iterable[int]) -> dict[int, frozenset[Weekday]]:
        """入れてある根だけ。"""

    @abstractmethod
    def set_workdays(self, project_id: int, workdays: frozenset[Weekday]) -> None: ...

    @abstractmethod
    def team_days_off(
        self, project_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[TeamDayOff]:
        """日付の順。"""

    @abstractmethod
    def add_team_day_off(self, day_off: TeamDayOff) -> None:
        """同じ日があれば名前を書き換える。"""

    @abstractmethod
    def remove_team_day_off(self, project_id: int, day: date) -> None: ...

    @abstractmethod
    def forget_team(self, project_id: int) -> None:
        """根でなくなる・消すときに、曜日と休日を全部消す。"""

    @abstractmethod
    def member_days_off(
        self, user_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[MemberDayOff]:
        """日付の順。"""

    @abstractmethod
    def add_member_day_off(self, day_off: MemberDayOff) -> None:
        """同じ日があれば何もしない。"""

    @abstractmethod
    def remove_member_day_off(self, user_id: int, day: date) -> None: ...
