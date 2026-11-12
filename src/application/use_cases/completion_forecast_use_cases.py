"""Give the forecast completion date for every task visible to the viewer (task #555 / ADR-0058).

The calculation is the domain's ``CompletionForecaster``. This only gathers and passes the visible tasks, dependencies, actuals, the capacity per assignee x root
(daily hours x allocation rate, the person's days off and that day's working hours), and the calendar per project (the root's weekdays overlaid with the holidays
and extra working days of the project and its ancestors, ADR-0059, ADR-0060).
Nothing is stored (decision 4: computed on the spot every time).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.application.user_clock import UserClock
from src.domain.entities.task import Task
from src.domain.services.completion_forecast import (
    HORIZON_DAYS,
    CompletionForecast,
    CompletionForecaster,
    SeatKey,
    TeamCalendar,
    WorkSeat,
)
from src.domain.services.project_calendar import layer_calendar_days
from src.domain.services.project_tree import ProjectTree
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.team_calendar_repository import (
    SqlAlchemyTeamCalendarRepository,
)


class CompletionForecastUseCases:
    def __init__(self, session: Session, clock: UserClock | None = None) -> None:
        self._tasks = SqlAlchemyTaskRepository(session)
        self._dependencies = SqlAlchemyTaskDependencyRepository(session)
        self._projects = SqlAlchemyProjectRepository(session)
        self._members = SqlAlchemyProjectMemberRepository(session)
        self._team_calendar = SqlAlchemyTeamCalendarRepository(session)
        self._clock = clock or UserClock(session)

    def forecast(self, user_id: int) -> CompletionForecast:
        """Forecasts for every task visible to the viewer (excluding archived ones). "Today" is the viewer's date."""
        today = self._clock.today(user_id)
        tasks = [t for t in self._tasks.find_all(user_id, {}) if not t.is_archived]
        tree = ProjectTree(self._projects.find_all(user_id))

        def root_of(project_id: int | None) -> int | None:
            if project_id is None or project_id not in tree:
                return None
            return tree.root_of(project_id)

        board = TaskProgressBoard(tasks, self._tasks.get_actual_hours_by_task(user_id))
        calendars = self._calendars(tasks, tree, today)
        return CompletionForecaster(today=today).forecast(
            tasks=tasks,
            board=board,
            dependencies=self._dependencies.find_all_for_user(user_id),
            seats=self._seats(tasks, root_of, calendars, today),
            root_of=root_of,
            project_calendar=lambda project_id: calendars.get(project_id) if project_id is not None else None,
        )

    def _calendars(self, tasks: list[Task], tree: ProjectTree, today: date) -> dict[int, TeamCalendar]:
        """Projects that have tasks, and their root's calendar (the root's weekdays overlaid with the holidays/extra working days of the project and its ancestors)."""
        last_day = today + timedelta(days=HORIZON_DAYS)
        projects = {t.project_id for t in tasks if t.project_id is not None and t.project_id in tree}
        projects |= {tree.root_of(p) for p in projects}
        lineages = {p: tree.ancestors_or_self(p) for p in projects}
        involved = {a for lineage in lineages.values() for a in lineage}
        days_off = self._team_calendar.team_days_off(involved, today, last_day)
        extra = self._team_calendar.extra_workdays(involved, today, last_day)
        roots = {lineage[-1] for lineage in lineages.values()}
        workdays = self._team_calendar.workdays_by_project(roots)
        calendars: dict[int, TeamCalendar] = {}
        for project_id, lineage in lineages.items():
            layered = layer_calendar_days(lineage, days_off, extra)
            calendars[project_id] = TeamCalendar(
                workdays=workdays.get(lineage[-1], WEEKDAYS_MON_TO_FRI),
                days_off=frozenset(d.day for d in layered.days_off),
                extra_workdays=frozenset(d.day for d in layered.extra_workdays),
            )
        return calendars

    def _seats(
        self,
        tasks: list[Task],
        root_of: Callable[[int | None], int | None],
        calendars: dict[int, TeamCalendar],
        today: date,
    ) -> dict[SeatKey, WorkSeat]:
        last_day = today + timedelta(days=HORIZON_DAYS)
        roots = {r for r in (root_of(t.project_id) for t in tasks) if r is not None}
        members = {root: self._members.find_by_project(root) for root in roots}
        people = {m.user_id for ms in members.values() for m in ms}
        # An unclassified task's assignee is only its creator (ADR-0055). Subtract that person's days off too
        people |= {t.assignee_user_id for t in tasks if t.project_id is None and t.assignee_user_id is not None}
        leave: dict[int, dict[date, int]] = defaultdict(dict)
        day_hours: dict[int, dict[date, float]] = defaultdict(dict)
        for day_off in self._team_calendar.member_days_off(people, today, last_day):
            if day_off.hours is not None:
                day_hours[day_off.user_id][day_off.day] = day_off.hours
            else:
                leave[day_off.user_id][day_off.day] = day_off.off_percent

        seats: dict[SeatKey, WorkSeat] = {}
        for root, ms in members.items():
            for m in ms:
                seats[(m.user_id, root)] = WorkSeat(
                    daily_hours=float(m.daily_hours),
                    engagement_percent=m.engagement_percent,
                    calendar=calendars.get(root, TeamCalendar()),
                    leave=leave[m.user_id],
                    day_hours=day_hours[m.user_id],
                )
        # Unclassified: 8 hours a day, 100%, Monday-Friday, no team holidays (ADR-0058 decision 1)
        for task in tasks:
            if task.project_id is None and task.assignee_user_id is not None:
                key: SeatKey = (task.assignee_user_id, None)
                if key not in seats:
                    seats[key] = WorkSeat(
                        leave=leave[task.assignee_user_id], day_hours=day_hours[task.assignee_user_id],
                    )
        return seats


__all__ = ["CompletionForecastUseCases"]
