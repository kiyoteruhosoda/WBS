"""View and edit a project's calendar (working weekdays, holidays) and each person's days off (ADR-0058 decision 2, ADR-0059).

- Working weekdays belong to the top-level project. Whichever level's id is passed, the root's are used
- Holidays and extra working days (days worked on a non-working weekday, ADR-0060) belong to the project they are added to. Shown are those of the project itself and its ancestors (up to the root)
  (lower projects inherit their parents'. On the same day the nearer one wins)
- Only the root's admins can edit weekdays and holidays
- Personal days off and that day's working hours belong to the person (the same across projects). Those of this tree's members are shown;
  only the person themselves and admins can edit them
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.team_day_off import (
    FULL_DAY_OFF_PERCENT,
    MemberDayOff,
    TeamDayOff,
    TeamExtraWorkday,
    team_day_off_name,
)
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.services.japanese_national_holidays import japanese_national_holidays
from src.domain.services.project_calendar import layer_calendar_days
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.team_calendar_repository import (
    SqlAlchemyTeamCalendarRepository,
)


@dataclass(frozen=True)
class TeamCalendarView:
    #: The opened project (where holidays are added)
    project_id: int
    #: The top-level project that holds the weekdays
    root_project_id: int
    #: Whether the caller is an admin in this tree (can edit weekdays, holidays, and anyone's days off)
    can_manage: bool
    workdays: list[Weekday]
    #: Holidays of the project and its ancestors (those whose ``project_id`` is not this one are inherited)
    days_off: list[TeamDayOff]
    #: Extra working days of the project and its ancestors (days worked on a non-working weekday; likewise)
    extra_workdays: list[TeamExtraWorkday]
    #: Days off of this tree's members and that day's working hours (date, ratio and hours only)
    leave: list[MemberDayOff]


class TeamCalendarUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._calendar = SqlAlchemyTeamCalendarRepository(session)
        self._members = SqlAlchemyProjectMemberRepository(session)
        self._membership = ProjectMembership(
            projects=SqlAlchemyProjectRepository(session),
            tasks=SqlAlchemyTaskRepository(session),
            milestones=SqlAlchemyMilestoneRepository(session),
            members=self._members,
        )

    def view(
        self, user_id: int, project_id: int, from_date: date | None = None, to_date: date | None = None,
    ) -> TeamCalendarView:
        root = self._root_of(user_id, project_id)
        mine = self._members.find(root, user_id)
        workdays = self._calendar.workdays(root)
        lineage = self._membership.tree(user_id).ancestors_or_self(project_id)
        layered = layer_calendar_days(
            lineage,
            self._calendar.team_days_off(lineage, from_date, to_date),
            self._calendar.extra_workdays(lineage, from_date, to_date),
        )
        return TeamCalendarView(
            project_id=project_id,
            root_project_id=root,
            can_manage=mine is not None and mine.is_manager,
            workdays=sorted(workdays if workdays is not None else WEEKDAYS_MON_TO_FRI, key=lambda w: w.iso_index),
            days_off=layered.days_off,
            extra_workdays=layered.extra_workdays,
            leave=self._calendar.member_days_off(self._membership.member_ids(root), from_date, to_date),
        )

    def set_workdays(self, user_id: int, project_id: int, workdays: list[Weekday]) -> TeamCalendarView:
        root = self._managed_root(user_id, project_id)
        if not workdays:
            raise ValidationError("a team needs at least one workday")
        self._calendar.set_workdays(root, frozenset(workdays))
        self._session.commit()
        return self.view(user_id, project_id)

    def add_day_off(self, user_id: int, project_id: int, day: date, name: str | None) -> TeamCalendarView:
        """Add a holiday to the opened project (if the same day exists, rename it)."""
        self._managed_root(user_id, project_id)
        # Do not keep both a holiday and an extra working day on the same day of the same project
        self._calendar.remove_extra_workday(project_id, day)
        self._calendar.add_team_day_off(TeamDayOff(project_id=project_id, day=day, name=team_day_off_name(name)))
        self._session.commit()
        return self.view(user_id, project_id)

    def remove_day_off(self, user_id: int, project_id: int, day: date) -> TeamCalendarView:
        """Only the opened project's own holidays can be deleted (inherited ones are deleted on the parent)."""
        self._managed_root(user_id, project_id)
        self._calendar.remove_team_day_off(project_id, day)
        self._session.commit()
        return self.view(user_id, project_id)

    def add_extra_workday(self, user_id: int, project_id: int, day: date, name: str | None) -> TeamCalendarView:
        """Add an extra working day (a day worked on a non-working weekday) to the opened project. Removes a holiday on the same day (ADR-0060)."""
        self._managed_root(user_id, project_id)
        self._calendar.remove_team_day_off(project_id, day)
        self._calendar.add_extra_workday(
            TeamExtraWorkday(project_id=project_id, day=day, name=team_day_off_name(name))
        )
        self._session.commit()
        return self.view(user_id, project_id)

    def remove_extra_workday(self, user_id: int, project_id: int, day: date) -> TeamCalendarView:
        """Only the opened project's own extra working days can be deleted."""
        self._managed_root(user_id, project_id)
        self._calendar.remove_extra_workday(project_id, day)
        self._session.commit()
        return self.view(user_id, project_id)

    def import_japanese_holidays(self, user_id: int, project_id: int, year: int) -> TeamCalendarView:
        """Add that year's Japanese national holidays, substitute holidays and citizens' holidays to the opened project (days already present on it or an ancestor are left as is)."""
        self._managed_root(user_id, project_id)
        lineage = self._membership.tree(user_id).ancestors_or_self(project_id)
        existing = {d.day for d in self._calendar.team_days_off(lineage, date(year, 1, 1), date(year, 12, 31))}
        for holiday in japanese_national_holidays(year):
            if holiday.date not in existing:
                self._calendar.add_team_day_off(
                    TeamDayOff(project_id=project_id, day=holiday.date, name=holiday.name)
                )
        self._session.commit()
        return self.view(user_id, project_id)

    def add_leave(
        self,
        user_id: int,
        project_id: int,
        member_user_id: int,
        day: date,
        off_percent: int = FULL_DAY_OFF_PERCENT,
        hours: float | None = None,
    ) -> TeamCalendarView:
        """Set a personal day off, or that day's working hours (``hours``: overtime, short day, holiday work) (overwrites the same day).
        Only the person themselves or an admin of this tree (the target must be a member of this tree)."""
        self._leave_editable(user_id, project_id, member_user_id)
        self._calendar.add_member_day_off(
            MemberDayOff(user_id=member_user_id, day=day, off_percent=off_percent, hours=hours)
        )
        self._session.commit()
        return self.view(user_id, project_id)

    def remove_leave(self, user_id: int, project_id: int, member_user_id: int, day: date) -> TeamCalendarView:
        self._leave_editable(user_id, project_id, member_user_id)
        self._calendar.remove_member_day_off(member_user_id, day)
        self._session.commit()
        return self.view(user_id, project_id)

    def _root_of(self, user_id: int, project_id: int) -> int:
        self._membership.visible_project(user_id, project_id)  # 404 if not visible
        return self._membership.tree(user_id).root_of(project_id)

    def _managed_root(self, user_id: int, project_id: int) -> int:
        root = self._root_of(user_id, project_id)
        self._membership.require_manager(user_id, root)
        return root

    def _leave_editable(self, user_id: int, project_id: int, member_user_id: int) -> None:
        root = self._root_of(user_id, project_id)
        if self._members.find(root, member_user_id) is None:
            raise NotFoundError("ProjectMember", member_user_id)
        if member_user_id != user_id:
            self._membership.require_manager(user_id, root)



__all__ = ["TeamCalendarUseCases", "TeamCalendarView"]
