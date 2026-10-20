from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.team_day_off import MemberDayOff, TeamDayOff, TeamExtraWorkday
from src.domain.repositories.team_calendar_repository import TeamCalendarRepository
from src.domain.value_objects.recurrence import Weekday
from src.infrastructure.database.models import (
    MemberDayOffModel,
    TeamDayOffModel,
    TeamExtraWorkdayModel,
    TeamWorkweekModel,
)

_WORKDAY_SEPARATOR = ","


class SqlAlchemyTeamCalendarRepository(TeamCalendarRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def workdays(self, project_id: int) -> frozenset[Weekday] | None:
        return self.workdays_by_project([project_id]).get(project_id)

    def workdays_by_project(self, project_ids: Iterable[int]) -> dict[int, frozenset[Weekday]]:
        ids = list(project_ids)
        if not ids:
            return {}
        stmt = select(TeamWorkweekModel).where(TeamWorkweekModel.project_id.in_(ids))
        return {m.project_id: _parse(m.workdays) for m in self._session.scalars(stmt)}

    def set_workdays(self, project_id: int, workdays: frozenset[Weekday]) -> None:
        model = self._session.scalar(select(TeamWorkweekModel).where(TeamWorkweekModel.project_id == project_id))
        text = _WORKDAY_SEPARATOR.join(w.value for w in sorted(workdays, key=lambda w: w.iso_index))
        if model is None:
            self._session.add(TeamWorkweekModel(project_id=project_id, workdays=text))
        else:
            model.workdays = text
        self._session.flush()

    def team_days_off(
        self, project_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[TeamDayOff]:
        ids = list(project_ids)
        if not ids:
            return []
        stmt = select(TeamDayOffModel).where(TeamDayOffModel.project_id.in_(ids))
        if from_date is not None:
            stmt = stmt.where(TeamDayOffModel.day >= from_date)
        if to_date is not None:
            stmt = stmt.where(TeamDayOffModel.day <= to_date)
        stmt = stmt.order_by(TeamDayOffModel.day, TeamDayOffModel.id)
        return [TeamDayOff(project_id=m.project_id, day=m.day, name=m.name) for m in self._session.scalars(stmt)]

    def add_team_day_off(self, day_off: TeamDayOff) -> None:
        model = self._session.scalar(
            select(TeamDayOffModel).where(
                TeamDayOffModel.project_id == day_off.project_id, TeamDayOffModel.day == day_off.day,
            )
        )
        if model is None:
            self._session.add(TeamDayOffModel(project_id=day_off.project_id, day=day_off.day, name=day_off.name))
        else:
            model.name = day_off.name
        self._session.flush()

    def remove_team_day_off(self, project_id: int, day: date) -> None:
        self._session.execute(
            delete(TeamDayOffModel).where(TeamDayOffModel.project_id == project_id, TeamDayOffModel.day == day)
        )
        self._session.flush()

    def extra_workdays(
        self, project_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[TeamExtraWorkday]:
        ids = list(project_ids)
        if not ids:
            return []
        stmt = select(TeamExtraWorkdayModel).where(TeamExtraWorkdayModel.project_id.in_(ids))
        if from_date is not None:
            stmt = stmt.where(TeamExtraWorkdayModel.day >= from_date)
        if to_date is not None:
            stmt = stmt.where(TeamExtraWorkdayModel.day <= to_date)
        stmt = stmt.order_by(TeamExtraWorkdayModel.day, TeamExtraWorkdayModel.id)
        return [
            TeamExtraWorkday(project_id=m.project_id, day=m.day, name=m.name) for m in self._session.scalars(stmt)
        ]

    def add_extra_workday(self, workday: TeamExtraWorkday) -> None:
        model = self._session.scalar(
            select(TeamExtraWorkdayModel).where(
                TeamExtraWorkdayModel.project_id == workday.project_id, TeamExtraWorkdayModel.day == workday.day,
            )
        )
        if model is None:
            self._session.add(
                TeamExtraWorkdayModel(project_id=workday.project_id, day=workday.day, name=workday.name)
            )
        else:
            model.name = workday.name
        self._session.flush()

    def remove_extra_workday(self, project_id: int, day: date) -> None:
        self._session.execute(
            delete(TeamExtraWorkdayModel).where(
                TeamExtraWorkdayModel.project_id == project_id, TeamExtraWorkdayModel.day == day,
            )
        )
        self._session.flush()

    def forget_workdays(self, project_id: int) -> None:
        self._session.execute(delete(TeamWorkweekModel).where(TeamWorkweekModel.project_id == project_id))
        self._session.flush()

    def member_days_off(
        self, user_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None,
    ) -> list[MemberDayOff]:
        ids = list(user_ids)
        if not ids:
            return []
        stmt = select(MemberDayOffModel).where(MemberDayOffModel.user_id.in_(ids))
        if from_date is not None:
            stmt = stmt.where(MemberDayOffModel.day >= from_date)
        if to_date is not None:
            stmt = stmt.where(MemberDayOffModel.day <= to_date)
        stmt = stmt.order_by(MemberDayOffModel.day, MemberDayOffModel.user_id)
        return [
            MemberDayOff(
                user_id=m.user_id, day=m.day, off_percent=m.off_percent,
                hours=float(m.hours) if m.hours is not None else None,
            )
            for m in self._session.scalars(stmt)
        ]

    def add_member_day_off(self, day_off: MemberDayOff) -> None:
        model = self._session.scalar(
            select(MemberDayOffModel).where(
                MemberDayOffModel.user_id == day_off.user_id, MemberDayOffModel.day == day_off.day,
            )
        )
        if model is None:
            self._session.add(
                MemberDayOffModel(
                    user_id=day_off.user_id, day=day_off.day, off_percent=day_off.off_percent, hours=_hours(day_off),
                )
            )
        else:
            model.off_percent = day_off.off_percent
            model.hours = _hours(day_off)
        self._session.flush()

    def remove_member_day_off(self, user_id: int, day: date) -> None:
        self._session.execute(
            delete(MemberDayOffModel).where(MemberDayOffModel.user_id == user_id, MemberDayOffModel.day == day)
        )
        self._session.flush()


def _hours(day_off: MemberDayOff) -> Decimal | None:
    return Decimal(str(day_off.hours)) if day_off.hours is not None else None


def _parse(text: str) -> frozenset[Weekday]:
    return frozenset(Weekday(code) for code in text.split(_WORKDAY_SEPARATOR) if code)
