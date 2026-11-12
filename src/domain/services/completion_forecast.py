"""Forecast finish dates by stacking remaining time onto assignees' free time (task #555, ADR-0058).

Each assignee × top-level project is one "seat" (``WorkSeat``), advanced one day at a time from today.

- Hours available on a day = hours per day × allocation (minus the leave ratio on the person's leave days). On days where the person set
  that day's working hours (overtime, short day, working on a day off), those hours × allocation (ADR-0060)
- A task advances only on days that are working days in its project's calendar, or days the person set working hours.
  A project's calendar is the root's weekdays overlaid with the days off and working days of itself and its ancestors (nearest wins. ADR-0059, ADR-0060).
  Time for tasks that cannot advance goes to the same person's other tasks
- First "ratio × that day's hours" goes to tasks with an assignment ratio, then the remaining time goes to tasks without a ratio in order
  (due date → priority → planned start date → number). Tasks waiting on dependencies are skipped
- Tasks with children use no time; they combine the forecasts of their descendant leaves

Touches nothing external (DB, clock). The caller passes "today".
"""

from __future__ import annotations

import enum
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.domain.entities.milestone import Milestone
from src.domain.entities.task import Task
from src.domain.entities.task_dependency import TaskDependency
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.dependency_type import DependencyType
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday
from src.domain.value_objects.task_status import TaskStatus

HORIZON_DAYS = 3 * 366
"""Forecast horizon (from today). Anything beyond it is "more than 3 years out"."""

DEFAULT_DAILY_HOURS = 8.0
DEFAULT_ENGAGEMENT_PERCENT = 100

_EPSILON = 1e-9

SeatKey = tuple[int, int | None]
"""Seat key = (assignee's user id, top-level project id; None for unclassified)."""


class ForecastGap(enum.StrEnum):
    """Why no forecast is given."""

    FINISHED = "finished"
    """Done, cancelled or remaining 0 (treated as finished; satisfies dependencies of later tasks)."""
    NO_ASSIGNEE = "no_assignee"
    NO_REMAINING = "no_remaining"
    """Remaining is undetermined (both remaining and estimate empty)."""
    NO_CAPACITY = "no_capacity"
    """The assignee has no free time (not a member, hours per day or allocation is 0, no working weekdays)."""
    WAITING = "waiting"
    """A preceding task has no forecast, or the dependencies form a cycle."""
    CHILD_UNFORECAST = "child_unforecast"
    """A descendant leaf has no forecast (task with children)."""
    BEYOND_HORIZON = "beyond_horizon"


@dataclass(frozen=True)
class TeamCalendar:
    """Project calendar: the root's working weekdays, plus days off and working days (days worked on a non-working weekday). The two never overlap."""

    workdays: frozenset[Weekday] = WEEKDAYS_MON_TO_FRI
    days_off: frozenset[date] = frozenset()
    extra_workdays: frozenset[date] = frozenset()

    def is_working_day(self, day: date) -> bool:
        if day in self.extra_workdays:
            return True
        return Weekday.of(day) in self.workdays and day not in self.days_off


@dataclass(frozen=True)
class WorkSeat:
    """Time the assignee can spend on that project (ADR-0058 decisions 1 and 2)."""

    daily_hours: float = DEFAULT_DAILY_HOURS
    engagement_percent: int = DEFAULT_ENGAGEMENT_PERCENT
    calendar: TeamCalendar = field(default_factory=TeamCalendar)
    leave: Mapping[date, int] = field(default_factory=dict)
    """Person's leave day → leave ratio (full day 100, half day 50; the same across projects. ADR-0059 decision 2)."""
    day_hours: Mapping[date, float] = field(default_factory=dict)
    """Day the person set working hours → hours (overtime, short day, working on a day off; the same across projects. ADR-0060)."""

    @property
    def _engagement(self) -> float:
        return max(min(self.engagement_percent, 100), 0) / 100

    @property
    def hours_per_day(self) -> float:
        return max(self.daily_hours, 0.0) * self._engagement

    @property
    def has_capacity(self) -> bool:
        if self._engagement <= _EPSILON:
            return False
        usual = self.hours_per_day > _EPSILON and bool(self.calendar.workdays)
        return usual or any(h > _EPSILON for h in self.day_hours.values())

    def person_hours(self, day: date) -> float:
        """Hours this person can spend on this project that day (ignores whether it is a working day)."""
        if day in self.day_hours:
            return max(self.day_hours[day], 0.0) * self._engagement
        off_percent = max(min(self.leave.get(day, 0), 100), 0)
        return self.hours_per_day * (100 - off_percent) / 100

    def works_on(self, day: date, calendar: TeamCalendar) -> bool:
        """Whether tasks of that calendar advance that day. Days with set working hours advance even on days off or non-working weekdays."""
        if self.day_hours.get(day, 0) > _EPSILON:
            return True
        return calendar.is_working_day(day)

    def hours_on(self, day: date) -> float:
        """Hours available that day under the root's calendar."""
        return self.person_hours(day) if self.works_on(day, self.calendar) else 0.0


@dataclass(frozen=True)
class TaskForecast:
    task_id: int
    start: date | None = None
    finish: date | None = None
    gap: ForecastGap | None = None
    """Why no forecast is given (None when one is)."""
    overdue_days: int = 0
    """Calendar days by which the forecast finish exceeds the due date (0 if it does not)."""

    @property
    def is_overdue(self) -> bool:
        return self.overdue_days > 0


@dataclass(frozen=True)
class MilestoneForecast:
    milestone_id: int
    finish: date | None
    """Latest forecast finish among the attached open tasks."""
    unforecast_count: int
    """Number of tasks without a forecast (if any, ``finish`` means "at least")."""
    overdue_days: int = 0


@dataclass
class _Leaf:
    task: Task
    seat_key: SeatKey
    remaining: float
    started_before_today: bool
    #: Calendar of this task's project (None means the seat's = root's calendar. ADR-0059 decision 1)
    calendar: TeamCalendar | None = None
    start: date | None = None
    finish: date | None = None


@dataclass(frozen=True)
class _Constraint:
    predecessor_id: int
    kind: DependencyType
    lag_days: int


class CompletionForecast:
    """Result of the computation. Look up forecasts for tasks and milestones."""

    def __init__(self, by_task: Mapping[int, TaskForecast], tasks: Iterable[Task]) -> None:
        self._by_task = dict(by_task)
        self._tasks = list(tasks)

    def task(self, task_id: int) -> TaskForecast:
        return self._by_task.get(task_id, TaskForecast(task_id, gap=ForecastGap.FINISHED))

    def milestone(self, milestone: Milestone) -> MilestoneForecast:
        finish: date | None = None
        unforecast = 0
        for task in self._tasks:
            if task.id is None or task.milestone_id != milestone.id:
                continue
            forecast = self.task(task.id)
            if forecast.gap is ForecastGap.FINISHED:
                continue
            if forecast.finish is None:
                unforecast += 1
                continue
            finish = forecast.finish if finish is None else max(finish, forecast.finish)
        return MilestoneForecast(
            milestone_id=milestone.id or 0,
            finish=finish,
            unforecast_count=unforecast,
            overdue_days=_overdue_days(finish, milestone.due_date),
        )


class CompletionForecaster:
    def __init__(self, *, today: date, horizon_days: int = HORIZON_DAYS) -> None:
        self._today = today
        self._last_day = today + timedelta(days=horizon_days - 1)

    def forecast(
        self,
        *,
        tasks: Iterable[Task],
        board: TaskProgressBoard,
        dependencies: Iterable[TaskDependency],
        seats: Mapping[SeatKey, WorkSeat],
        root_of: Callable[[int | None], int | None],
        project_calendar: Callable[[int | None], TeamCalendar | None] = lambda _: None,
    ) -> CompletionForecast:
        """``tasks`` is everything except deleted and archived tasks (pass it unfiltered, to count dependencies and tasks in the same seat).

        ``project_calendar`` returns, for a project id, that project's calendar (the root's weekdays overlaid with the days off and working days
        of itself and its ancestors). If None, the assignee's seat calendar (the root's) is used.
        """
        tasks = [t for t in tasks if t.id is not None]
        by_id = {t.id: t for t in tasks}
        result: dict[int, TaskForecast] = {}
        leaves: dict[int, _Leaf] = {}
        for task in tasks:
            if board.has_subtasks(task.id):
                continue
            gap, leaf = self._classify(task, board, seats, root_of)
            if gap is not None:
                result[task.id] = TaskForecast(task.id, gap=gap)
            else:
                leaf.calendar = project_calendar(task.project_id)
                leaves[task.id] = leaf

        constraints = self._constraints(dependencies, by_id, board)
        self._wait_for_unforecast(leaves, result, constraints, board)
        self._simulate(leaves, constraints, seats, board, result)

        for task_id, leaf in leaves.items():
            result[task_id] = TaskForecast(
                task_id, start=leaf.start, finish=leaf.finish,
                overdue_days=_overdue_days(leaf.finish, leaf.task.due_date),
            )
        for task in tasks:
            if board.has_subtasks(task.id):
                result[task.id] = self._roll_up(task, board, result)
        return CompletionForecast(result, tasks)

    # ---- Classify -----------------------------------------------------------

    def _classify(
        self,
        task: Task,
        board: TaskProgressBoard,
        seats: Mapping[SeatKey, WorkSeat],
        root_of: Callable[[int | None], int | None],
    ) -> tuple[ForecastGap | None, _Leaf | None]:
        if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            return ForecastGap.FINISHED, None
        actual = board.actual_hours(task.id)
        remaining = task.remaining_hours_from(actual)
        if remaining is None:
            return ForecastGap.NO_REMAINING, None
        if remaining <= _EPSILON:
            return ForecastGap.FINISHED, None
        if task.assignee_user_id is None:
            return ForecastGap.NO_ASSIGNEE, None
        key: SeatKey = (task.assignee_user_id, root_of(task.project_id))
        seat = seats.get(key)
        if seat is None or not seat.has_capacity:
            return ForecastGap.NO_CAPACITY, None
        started = actual > 0 or task.status == TaskStatus.DOING
        return None, _Leaf(task=task, seat_key=key, remaining=remaining, started_before_today=started)

    def _constraints(
        self,
        dependencies: Iterable[TaskDependency],
        by_id: Mapping[int, Task],
        board: TaskProgressBoard,
    ) -> dict[int, list[_Constraint]]:
        """Dependencies per leaf. If the later task has children, apply to each of its descendant leaves."""
        constraints: dict[int, list[_Constraint]] = defaultdict(list)
        for dep in dependencies:
            if dep.predecessor_task_id not in by_id or dep.successor_task_id not in by_id:
                continue
            constraint = _Constraint(dep.predecessor_task_id, dep.dependency_type, dep.lag_days)
            for leaf_id in self._leaf_ids(dep.successor_task_id, board):
                constraints[leaf_id].append(constraint)
        return constraints

    @staticmethod
    def _leaf_ids(task_id: int, board: TaskProgressBoard) -> list[int]:
        if not board.has_subtasks(task_id):
            return [task_id]
        return [t.id for t in board.descendants(task_id) if not board.has_subtasks(t.id)]

    def _wait_for_unforecast(
        self,
        leaves: dict[int, _Leaf],
        result: dict[int, TaskForecast],
        constraints: Mapping[int, list[_Constraint]],
        board: TaskProgressBoard,
    ) -> None:
        """If a preceding task has no forecast, the later task gets none either ("waiting on a preceding task")."""
        changed = True
        while changed:
            changed = False
            for leaf_id in list(leaves):
                for c in constraints.get(leaf_id, ()):
                    if self._is_unforecast(c.predecessor_id, leaves, result, board):
                        del leaves[leaf_id]
                        result[leaf_id] = TaskForecast(leaf_id, gap=ForecastGap.WAITING)
                        changed = True
                        break

    def _is_unforecast(
        self, task_id: int, leaves: Mapping[int, _Leaf], result: Mapping[int, TaskForecast], board: TaskProgressBoard,
    ) -> bool:
        for leaf_id in self._leaf_ids(task_id, board):
            if leaf_id in leaves:
                continue
            forecast = result.get(leaf_id)
            if forecast is not None and forecast.gap is not ForecastGap.FINISHED:
                return True
        return False

    # ---- Advance one day at a time ----------------------------------------------

    def _simulate(
        self,
        leaves: dict[int, _Leaf],
        constraints: Mapping[int, list[_Constraint]],
        seats: Mapping[SeatKey, WorkSeat],
        board: TaskProgressBoard,
        result: dict[int, TaskForecast],
    ) -> None:
        by_seat: dict[SeatKey, list[_Leaf]] = defaultdict(list)
        for leaf in leaves.values():
            by_seat[leaf.seat_key].append(leaf)
        for queue in by_seat.values():
            queue.sort(key=_queue_order)

        open_count = len(leaves)
        day = self._today
        while open_count and day <= self._last_day:
            left = {key: seats[key].person_hours(day) for key in by_seat}
            capacity = dict(left)
            given_today: set[int] = set()
            progressed = True
            # With SS, a task can start the same day its predecessor starts. Re-distribute while new starts keep appearing
            while progressed:
                progressed = False
                for key, queue in by_seat.items():
                    if left[key] <= _EPSILON:
                        continue
                    seat = seats[key]
                    ready = [
                        leaf for leaf in queue
                        if leaf.finish is None and leaf.task.id not in given_today
                        and seat.works_on(day, leaf.calendar or seat.calendar)
                        and self._is_ready(leaf, day, constraints, leaves, board)
                    ]
                    if not ready:
                        continue
                    progressed = True
                    left[key] = self._hand_out(ready, capacity[key], left[key], day, given_today)
                    open_count -= sum(1 for leaf in ready if leaf.finish == day)
            day += timedelta(days=1)

        self._apply_finish_floors(leaves, constraints, board)
        # Not finished within the horizon: if never started and dependencies still unmet, it is "waiting on a preceding task" (including cycles)
        after_horizon = self._last_day + timedelta(days=1)
        unfinished = {
            leaf_id: leaf.start is None and any(
                not self._is_satisfied(c, after_horizon, leaves, board) for c in constraints.get(leaf_id, ())
            )
            for leaf_id, leaf in leaves.items() if leaf.finish is None
        }
        for leaf_id, waiting in unfinished.items():
            del leaves[leaf_id]
            result[leaf_id] = TaskForecast(
                leaf_id, gap=ForecastGap.WAITING if waiting else ForecastGap.BEYOND_HORIZON,
            )

    @staticmethod
    def _hand_out(ready: list[_Leaf], capacity: float, left: float, day: date, given_today: set[int]) -> float:
        """First "ratio × that day's hours" to tasks with a ratio, then the rest to tasks without a ratio in order."""
        shared = [leaf for leaf in ready if leaf.task.allocation_percent]
        total_percent = sum(leaf.task.allocation_percent or 0 for leaf in shared)
        scale = min(1.0, 100 / total_percent) if total_percent else 1.0
        for leaf in shared:
            share = capacity * (leaf.task.allocation_percent or 0) / 100 * scale
            left -= _work(leaf, min(share, left), day)
            given_today.add(leaf.task.id)
        for leaf in ready:
            if leaf.task.allocation_percent or left <= _EPSILON:
                continue
            left -= _work(leaf, left, day)
            given_today.add(leaf.task.id)
        return left

    def _is_ready(
        self,
        leaf: _Leaf,
        day: date,
        constraints: Mapping[int, list[_Constraint]],
        leaves: Mapping[int, _Leaf],
        board: TaskProgressBoard,
    ) -> bool:
        if leaf.task.start_date is not None and day < leaf.task.start_date:
            return False
        return all(self._is_satisfied(c, day, leaves, board) for c in constraints.get(leaf.task.id, ()))

    def _is_satisfied(
        self, c: _Constraint, day: date, leaves: Mapping[int, _Leaf], board: TaskProgressBoard,
    ) -> bool:
        lag = timedelta(days=c.lag_days)
        if c.kind == DependencyType.FS:
            finish = self._node_finish(c.predecessor_id, leaves, board)
            return finish is not None and day >= finish + timedelta(days=1) + lag
        if c.kind == DependencyType.SS:
            start = self._node_start(c.predecessor_id, leaves, board)
            return start is not None and day >= start + lag
        # FF and SF do not block starting (they only set a lower bound on the finish date. _apply_finish_floors)
        return True

    def _node_finish(self, task_id: int, leaves: Mapping[int, _Leaf], board: TaskProgressBoard) -> date | None:
        """Finish of the preceding task. Yesterday if already finished; None if it has no forecast yet."""
        latest = self._today - timedelta(days=1)
        for leaf_id in self._leaf_ids(task_id, board):
            leaf = leaves.get(leaf_id)
            if leaf is None:
                continue  # Finished (tasks without a forecast were removed in _wait_for_unforecast)
            if leaf.finish is None:
                return None
            latest = max(latest, leaf.finish)
        return latest

    def _node_start(self, task_id: int, leaves: Mapping[int, _Leaf], board: TaskProgressBoard) -> date | None:
        """Start of the preceding task. Yesterday if already started or finished; None if not started yet."""
        earliest: date | None = None
        for leaf_id in self._leaf_ids(task_id, board):
            leaf = leaves.get(leaf_id)
            if leaf is None or leaf.started_before_today:
                return self._today - timedelta(days=1)
            if leaf.start is not None:
                earliest = leaf.start if earliest is None else min(earliest, leaf.start)
        return earliest

    def _apply_finish_floors(
        self, leaves: dict[int, _Leaf], constraints: Mapping[int, list[_Constraint]], board: TaskProgressBoard,
    ) -> None:
        """Do not finish before the predecessor's finish (FF) or the predecessor's start (SF), plus lag."""
        for _ in range(len(leaves) + 1):
            changed = False
            for leaf_id, leaf in leaves.items():
                for c in constraints.get(leaf_id, ()):
                    if c.kind == DependencyType.FF:
                        base = self._node_finish(c.predecessor_id, leaves, board)
                    elif c.kind == DependencyType.SF:
                        base = self._node_start(c.predecessor_id, leaves, board)
                    else:
                        continue
                    if base is None or leaf.finish is None:
                        continue
                    floor = base + timedelta(days=c.lag_days)
                    if floor > leaf.finish:
                        leaf.finish = floor
                        changed = True
            if not changed:
                return

    # ---- Roll up ------------------------------------------------------------

    @staticmethod
    def _roll_up(task: Task, board: TaskProgressBoard, result: Mapping[int, TaskForecast]) -> TaskForecast:
        if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            return TaskForecast(task.id, gap=ForecastGap.FINISHED)
        starts: list[date] = []
        finishes: list[date] = []
        for node in board.descendants(task.id):
            if board.has_subtasks(node.id):
                continue
            forecast = result.get(node.id)
            if forecast is None or forecast.gap is ForecastGap.FINISHED:
                continue
            if forecast.finish is None:
                return TaskForecast(task.id, gap=ForecastGap.CHILD_UNFORECAST)
            finishes.append(forecast.finish)
            if forecast.start is not None:
                starts.append(forecast.start)
        if not finishes:
            return TaskForecast(task.id, gap=ForecastGap.FINISHED)
        finish = max(finishes)
        return TaskForecast(
            task.id, start=min(starts) if starts else None, finish=finish,
            overdue_days=_overdue_days(finish, task.due_date),
        )


def _work(leaf: _Leaf, hours: float, day: date) -> float:
    """Advance by up to ``hours`` and return the hours used."""
    used = min(max(hours, 0.0), leaf.remaining)
    if used <= _EPSILON:
        return 0.0
    if leaf.start is None:
        leaf.start = day
    leaf.remaining -= used
    if leaf.remaining <= _EPSILON:
        leaf.remaining = 0.0
        leaf.finish = day
    return used


def _queue_order(leaf: _Leaf) -> tuple:
    task = leaf.task
    return (
        task.due_date or date.max,
        -task.priority,
        task.start_date or date.max,
        task.id or 0,
    )


def _overdue_days(finish: date | None, due: date | None) -> int:
    if finish is None or due is None or finish <= due:
        return 0
    return (finish - due).days


__all__ = [
    "DEFAULT_DAILY_HOURS",
    "DEFAULT_ENGAGEMENT_PERCENT",
    "HORIZON_DAYS",
    "CompletionForecast",
    "CompletionForecaster",
    "ForecastGap",
    "MilestoneForecast",
    "SeatKey",
    "TaskForecast",
    "TeamCalendar",
    "WorkSeat",
]
