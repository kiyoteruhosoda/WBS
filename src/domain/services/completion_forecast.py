"""終わる見込みの日を、残りの時間を担当者の空きに積んで出す（task #555・ADR-0058）。

担当者 × いちばん上のプロジェクトを 1 つの「枠」（``WorkSeat``）とし、今日から 1 日ずつ進める。

- その日に使える時間 = 1 日の工数 × 従事率（稼働する曜日で、チームの休日でない日だけ。本人の休みの日は休む割合を引く）
- 下のプロジェクトで足した休日は、そのプロジェクトのタスクだけ進めない（ほかのタスクへ時間が回る。ADR-0059）
- まずアサイン比率のあるタスクへ「比率 × その日の時間」、残った時間を比率の無いタスクへ順番に
  （期限 → 優先度 → 計画の開始日 → 番号）。依存で待っているものは飛ばす
- 子を持つタスクは時間を使わず、子孫の葉の見込みを束ねる

外のもの（DB・時計）には触れない。「今日」は呼ぶ側が渡す。
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
"""見込みの先の限り（今日から）。越えるものは「3 年より先」。"""

DEFAULT_DAILY_HOURS = 8.0
DEFAULT_ENGAGEMENT_PERCENT = 100

_EPSILON = 1e-9

SeatKey = tuple[int, int | None]
"""枠の鍵 =（担当者の利用者 id, いちばん上のプロジェクトの id。未分類は None）。"""


class ForecastGap(enum.StrEnum):
    """見込みを出さない理由。"""

    FINISHED = "finished"
    """完了・中止・残 0（終わっている扱い。後のタスクの依存は満たす）。"""
    NO_ASSIGNEE = "no_assignee"
    NO_REMAINING = "no_remaining"
    """残が決まらない（残も見積も空）。"""
    NO_CAPACITY = "no_capacity"
    """担当者の空きが無い（メンバーでない・1 日の工数か従事率が 0・稼働する曜日が無い）。"""
    WAITING = "waiting"
    """先のタスクに見込みが出ない・依存が輪になっている。"""
    CHILD_UNFORECAST = "child_unforecast"
    """子孫の葉に見込みの出ないものがある（子を持つタスク）。"""
    BEYOND_HORIZON = "beyond_horizon"


@dataclass(frozen=True)
class TeamCalendar:
    """いちばん上のプロジェクトの稼働する曜日と休日。"""

    workdays: frozenset[Weekday] = WEEKDAYS_MON_TO_FRI
    days_off: frozenset[date] = frozenset()

    def is_working_day(self, day: date) -> bool:
        return Weekday.of(day) in self.workdays and day not in self.days_off


@dataclass(frozen=True)
class WorkSeat:
    """担当者がそのプロジェクトに使える時間（ADR-0058 決定 1・2）。"""

    daily_hours: float = DEFAULT_DAILY_HOURS
    engagement_percent: int = DEFAULT_ENGAGEMENT_PERCENT
    calendar: TeamCalendar = field(default_factory=TeamCalendar)
    leave: Mapping[date, int] = field(default_factory=dict)
    """本人の休みの日 → 休む割合（終日 100・半休 50。プロジェクトをまたいで同じ。ADR-0059 決定 2）。"""

    @property
    def hours_per_day(self) -> float:
        return max(self.daily_hours, 0.0) * max(min(self.engagement_percent, 100), 0) / 100

    @property
    def has_capacity(self) -> bool:
        return self.hours_per_day > _EPSILON and bool(self.calendar.workdays)

    def hours_on(self, day: date) -> float:
        if not self.calendar.is_working_day(day):
            return 0.0
        off_percent = max(min(self.leave.get(day, 0), 100), 0)
        return self.hours_per_day * (100 - off_percent) / 100


@dataclass(frozen=True)
class TaskForecast:
    task_id: int
    start: date | None = None
    finish: date | None = None
    gap: ForecastGap | None = None
    """見込みを出さないときの理由（出すときは None）。"""
    overdue_days: int = 0
    """見込みの終わりが期限を越える暦の日数（越えなければ 0）。"""

    @property
    def is_overdue(self) -> bool:
        return self.overdue_days > 0


@dataclass(frozen=True)
class MilestoneForecast:
    milestone_id: int
    finish: date | None
    """付いた開いているタスクの見込みの終わりのうち、いちばん遅い日。"""
    unforecast_count: int
    """見込みの出ないタスクの数（1 つでもあれば ``finish`` は「少なくとも」）。"""
    overdue_days: int = 0


@dataclass
class _Leaf:
    task: Task
    seat_key: SeatKey
    remaining: float
    started_before_today: bool
    #: このタスクのプロジェクトで足した休日（根のものは枠の空きに入っているので含めない。ADR-0059 決定 1）
    days_off: frozenset[date] = frozenset()
    start: date | None = None
    finish: date | None = None


@dataclass(frozen=True)
class _Constraint:
    predecessor_id: int
    kind: DependencyType
    lag_days: int


class CompletionForecast:
    """計算の結果。タスクとマイルストーンの見込みを引く。"""

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
        project_days_off: Callable[[int | None], frozenset[date]] = lambda _: frozenset(),
    ) -> CompletionForecast:
        """``tasks`` は削除・アーカイブを除いた全部（依存と同じ枠のタスクを数えるため、絞らずに渡す）。

        ``project_days_off`` はプロジェクトの id から、そのプロジェクトと根を除く先祖で足した休日を返す。
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
                leaf.days_off = project_days_off(task.project_id)
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

    # ---- 分ける -------------------------------------------------------------

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
        """葉ごとの依存。後のタスクが子を持つなら、その子孫の葉それぞれに効かせる。"""
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
        """先のタスクに見込みが出ないなら、後のタスクも出さない（「先のタスク待ち」）。"""
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

    # ---- 1 日ずつ進める ---------------------------------------------------------

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
            left = {key: seats[key].hours_on(day) for key in by_seat}
            capacity = dict(left)
            given_today: set[int] = set()
            progressed = True
            # SS の依存は、先のタスクが同じ日に始まれば同じ日に始められる。始まりが増える間、配り直す
            while progressed:
                progressed = False
                for key, queue in by_seat.items():
                    if left[key] <= _EPSILON:
                        continue
                    ready = [
                        leaf for leaf in queue
                        if leaf.finish is None and leaf.task.id not in given_today
                        and self._is_ready(leaf, day, constraints, leaves, board)
                    ]
                    if not ready:
                        continue
                    progressed = True
                    left[key] = self._hand_out(ready, capacity[key], left[key], day, given_today)
                    open_count -= sum(1 for leaf in ready if leaf.finish == day)
            day += timedelta(days=1)

        self._apply_finish_floors(leaves, constraints, board)
        # 限りまでに終わらないもの: 一度も始まらず依存を満たさないままなら「先のタスク待ち」（輪を含む）
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
        """比率のあるタスクへ先に「比率 × その日の時間」、残りを比率の無いタスクへ順番に。"""
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
        if day in leaf.days_off:
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
        # FF・SF は始めるのを止めない（終わりの日の下限だけ。_apply_finish_floors）
        return True

    def _node_finish(self, task_id: int, leaves: Mapping[int, _Leaf], board: TaskProgressBoard) -> date | None:
        """先のタスクの終わり。もう終わっているなら昨日、まだ見込みが無いなら None。"""
        latest = self._today - timedelta(days=1)
        for leaf_id in self._leaf_ids(task_id, board):
            leaf = leaves.get(leaf_id)
            if leaf is None:
                continue  # 終わっている（見込みの出ないものは _wait_for_unforecast で外した）
            if leaf.finish is None:
                return None
            latest = max(latest, leaf.finish)
        return latest

    def _node_start(self, task_id: int, leaves: Mapping[int, _Leaf], board: TaskProgressBoard) -> date | None:
        """先のタスクの始まり。もう始まっている・終わっているなら昨日、まだ始まらないなら None。"""
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
        """FF は先の終わり、SF は先の始まり（＋ずれ）より前に終わらせない。"""
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

    # ---- 束ねる -------------------------------------------------------------

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
    """``hours`` まで進め、使った時間を返す。"""
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
