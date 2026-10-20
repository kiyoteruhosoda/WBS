"""プロジェクトのカレンダー（稼働する曜日・休日）と、各人の休みを見る・入れる（ADR-0058 決定 2・ADR-0059）。

- 稼働する曜日はいちばん上のプロジェクトに付く。どの段の id で呼んでも根のものを扱う
- 休日は呼んだプロジェクトに付く。見せるのは自分と先祖（根まで）の休日（下のプロジェクトは親の休日を引き継ぐ）
- 曜日と休日を入れられるのは根の管理者だけ
- 各人の休みは人に付く（プロジェクトをまたいで同じ）。この木のメンバーの休みを見せ、入れられるのは本人と管理者だけ
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
    team_day_off_name,
)
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.services.japanese_national_holidays import japanese_national_holidays
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
    #: 開いたプロジェクト（休日を足す先）
    project_id: int
    #: 曜日が付いているいちばん上のプロジェクト
    root_project_id: int
    #: 自分がこの木で管理者か（曜日・休日と、だれの休みでも入れられる）
    can_manage: bool
    workdays: list[Weekday]
    #: 自分と先祖の休日（``project_id`` が自分でないものは引き継いだもの）
    days_off: list[TeamDayOff]
    #: この木のメンバーの休み（日付と休む割合だけ）
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
        return TeamCalendarView(
            project_id=project_id,
            root_project_id=root,
            can_manage=mine is not None and mine.is_manager,
            workdays=sorted(workdays if workdays is not None else WEEKDAYS_MON_TO_FRI, key=lambda w: w.iso_index),
            days_off=_nearest_first(self._calendar.team_days_off(lineage, from_date, to_date), lineage),
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
        """開いたプロジェクトに休日を足す（同じ日があれば名前を書き換える）。"""
        self._managed_root(user_id, project_id)
        self._calendar.add_team_day_off(TeamDayOff(project_id=project_id, day=day, name=team_day_off_name(name)))
        self._session.commit()
        return self.view(user_id, project_id)

    def remove_day_off(self, user_id: int, project_id: int, day: date) -> TeamCalendarView:
        """開いたプロジェクト自身の休日だけ消せる（親から引き継いだものは親で消す）。"""
        self._managed_root(user_id, project_id)
        self._calendar.remove_team_day_off(project_id, day)
        self._session.commit()
        return self.view(user_id, project_id)

    def import_japanese_holidays(self, user_id: int, project_id: int, year: int) -> TeamCalendarView:
        """開いたプロジェクトに、その年の日本の祝日・振替休日・国民の休日を足す（自分か先祖にすでにある日はそのまま）。"""
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
    ) -> TeamCalendarView:
        """各人の休みを足す（同じ日なら休む割合を書き換える）。本人か、この木の管理者だけ（相手はこの木のメンバー）。"""
        self._leave_editable(user_id, project_id, member_user_id)
        self._calendar.add_member_day_off(MemberDayOff(user_id=member_user_id, day=day, off_percent=off_percent))
        self._session.commit()
        return self.view(user_id, project_id)

    def remove_leave(self, user_id: int, project_id: int, member_user_id: int, day: date) -> TeamCalendarView:
        self._leave_editable(user_id, project_id, member_user_id)
        self._calendar.remove_member_day_off(member_user_id, day)
        self._session.commit()
        return self.view(user_id, project_id)

    def _root_of(self, user_id: int, project_id: int) -> int:
        self._membership.visible_project(user_id, project_id)  # 見えなければ 404
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


def _nearest_first(days_off: list[TeamDayOff], lineage: list[int]) -> list[TeamDayOff]:
    """同じ日が自分と先祖の両方にあれば、近いほう（自分）を 1 つだけ。日付の順。"""
    rank = {project_id: i for i, project_id in enumerate(lineage)}
    by_day: dict[date, TeamDayOff] = {}
    for day_off in days_off:
        kept = by_day.get(day_off.day)
        if kept is None or rank[day_off.project_id] < rank[kept.project_id]:
            by_day[day_off.day] = day_off
    return [by_day[day] for day in sorted(by_day)]


__all__ = ["TeamCalendarUseCases", "TeamCalendarView"]
