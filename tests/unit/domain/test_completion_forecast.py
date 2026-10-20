"""終わる見込みの日（task #555・ADR-0058）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.entities.milestone import Milestone
from src.domain.entities.task import Task
from src.domain.entities.task_dependency import TaskDependency
from src.domain.services.completion_forecast import (
    CompletionForecaster,
    ForecastGap,
    TeamCalendar,
    WorkSeat,
)
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.dependency_type import DependencyType
from src.domain.value_objects.recurrence import Weekday
from src.domain.value_objects.task_status import TaskStatus

MONDAY = date(2026, 11, 2)
PROJECT = 10
ALICE = 1
BOB = 2


def _task(task_id: int, assignee: int | None = ALICE, remaining: float | None = 8, **kwargs) -> Task:
    values = {
        "id": task_id,
        "user_id": ALICE,
        "title": f"t{task_id}",
        "project_id": PROJECT,
        "assignee_user_id": assignee,
        "remaining_hours": Decimal(str(remaining)) if remaining is not None else None,
    }
    values.update(kwargs)
    return Task(**values)


def _seat(daily: float = 8, engagement: int = 100, *, days_off=(), leave=(), workdays=None) -> WorkSeat:
    calendar = TeamCalendar(days_off=frozenset(days_off))
    if workdays is not None:
        calendar = TeamCalendar(workdays=frozenset(workdays), days_off=frozenset(days_off))
    # 休みは日付の集まり（終日）か、日付 → 休む割合
    off = leave if isinstance(leave, dict) else dict.fromkeys(leave, 100)
    return WorkSeat(daily_hours=daily, engagement_percent=engagement, calendar=calendar, leave=off)


def _forecast(tasks, seats, dependencies=(), *, actual=None, today=MONDAY, horizon_days=None):
    forecaster = (
        CompletionForecaster(today=today) if horizon_days is None
        else CompletionForecaster(today=today, horizon_days=horizon_days)
    )
    return forecaster.forecast(
        tasks=tasks,
        board=TaskProgressBoard(tasks, actual or {}),
        dependencies=dependencies,
        seats=seats,
        root_of=lambda project_id: project_id,
    )


def _fs(predecessor: int, successor: int, lag: int = 0, kind: DependencyType = DependencyType.FS) -> TaskDependency:
    return TaskDependency(predecessor_task_id=predecessor, successor_task_id=successor, dependency_type=kind, lag_days=lag)


def test_adr_0058_example() -> None:
    """ADR-0058「計算の例」の表と同じ（担当 2 人・チームの休日・本人の休み・比率・依存）。"""
    culture_day = date(2026, 11, 3)
    team_days_off = {culture_day}
    seats = {
        (ALICE, PROJECT): _seat(8, 50, days_off=team_days_off, leave={date(2026, 11, 5)}),
        (BOB, PROJECT): _seat(8, 75, days_off=team_days_off),
    }
    tasks = [
        _task(1, ALICE, 6, due_date=date(2026, 11, 6)),  # A1
        _task(2, ALICE, 4, allocation_percent=50),  # A2
        _task(3, ALICE, 4, due_date=date(2026, 11, 10)),  # A3
        _task(4, BOB, 9, due_date=date(2026, 11, 6)),  # B1（A1 の後）
        _task(5, None, 3),  # U
        _task(6, ALICE, 0, status=TaskStatus.DONE),  # D
    ]
    milestone = Milestone(id=7, user_id=ALICE, name="M")
    tasks[0].milestone_id = 7
    tasks[3].milestone_id = 7

    result = _forecast(tasks, seats, [_fs(1, 4)])

    a1, a2, a3, b1, u, d = (result.task(i) for i in range(1, 7))
    assert (a1.start, a1.finish, a1.overdue_days) == (date(2026, 11, 2), date(2026, 11, 6), 0)
    assert (a2.start, a2.finish) == (date(2026, 11, 2), date(2026, 11, 4))
    assert (a3.start, a3.finish, a3.overdue_days) == (date(2026, 11, 6), date(2026, 11, 9), 0)
    assert (b1.start, b1.finish, b1.overdue_days) == (date(2026, 11, 9), date(2026, 11, 10), 4)
    assert b1.is_overdue
    assert (u.finish, u.gap) == (None, ForecastGap.NO_ASSIGNEE)
    assert (d.finish, d.gap) == (None, ForecastGap.FINISHED)
    assert result.milestone(milestone).finish == date(2026, 11, 10)
    assert result.milestone(milestone).unforecast_count == 0


# ---- 見込みを出さないもの（#555 AC2） -----------------------------------------------


def test_done_cancelled_and_zero_remaining_get_no_forecast() -> None:
    tasks = [
        _task(1, status=TaskStatus.DONE),
        _task(2, status=TaskStatus.CANCELLED),
        _task(3, remaining=0),
    ]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    for task_id in (1, 2, 3):
        assert result.task(task_id).finish is None
        assert result.task(task_id).gap is ForecastGap.FINISHED


def test_task_without_assignee_gets_no_forecast() -> None:
    result = _forecast([_task(1, assignee=None)], {(ALICE, PROJECT): _seat()})
    assert result.task(1).gap is ForecastGap.NO_ASSIGNEE
    assert result.task(1).finish is None


def test_unknown_remaining_gets_no_forecast() -> None:
    result = _forecast([_task(1, remaining=None)], {(ALICE, PROJECT): _seat()})
    assert result.task(1).gap is ForecastGap.NO_REMAINING


def test_default_remaining_is_estimate_minus_actual() -> None:
    # 残が空なら 見積 − 実績（ADR-0010）。見積 12h・実績 4h → 残 8h = 1 日
    task = _task(1, remaining=None, estimated_hours=Decimal("12"))
    result = _forecast([task], {(ALICE, PROJECT): _seat()}, actual={1: 4.0})
    assert result.task(1).finish == MONDAY


def test_no_capacity_when_not_a_member_or_zero_engagement() -> None:
    tasks = [_task(1, ALICE), _task(2, BOB)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat(engagement=0)})
    assert result.task(1).gap is ForecastGap.NO_CAPACITY
    assert result.task(2).gap is ForecastGap.NO_CAPACITY  # BOB の枠が無い（メンバーでない）


def test_no_capacity_without_workdays() -> None:
    result = _forecast([_task(1)], {(ALICE, PROJECT): _seat(workdays=())})
    assert result.task(1).gap is ForecastGap.NO_CAPACITY


def test_beyond_horizon() -> None:
    result = _forecast([_task(1, remaining=100)], {(ALICE, PROJECT): _seat(1)}, horizon_days=10)
    assert result.task(1).gap is ForecastGap.BEYOND_HORIZON


# ---- 空きと休み（#554 AC2） ---------------------------------------------------------


def test_daily_hours_times_engagement() -> None:
    # 6 時間 × 50% = 3 時間/日。残 9h → 月・火・水
    result = _forecast([_task(1, remaining=9)], {(ALICE, PROJECT): _seat(6, 50)})
    assert result.task(1).finish == date(2026, 11, 4)


def test_team_days_off_and_leave_are_skipped() -> None:
    seat = _seat(8, days_off={date(2026, 11, 3)}, leave={date(2026, 11, 4)})
    result = _forecast([_task(1, remaining=16)], {(ALICE, PROJECT): seat})
    assert result.task(1).finish == date(2026, 11, 5)  # 月・(火休日)・(水休み)・木


def test_a_half_day_off_halves_the_hours_of_that_day() -> None:
    # ADR-0059 決定 2: 半休（50）の日は半分だけ
    seat = _seat(8, leave={date(2026, 11, 3): 50})
    result = _forecast([_task(1, remaining=16)], {(ALICE, PROJECT): seat})
    assert result.task(1).finish == date(2026, 11, 4)  # 月 8・火 4・水 4
    seat = _seat(8, leave={date(2026, 11, 3): 100})
    result = _forecast([_task(1, remaining=16)], {(ALICE, PROJECT): seat})
    assert result.task(1).finish == date(2026, 11, 4)  # 月 8・(火休み)・水 8


def test_days_off_of_a_sub_project_stop_only_its_tasks() -> None:
    # ADR-0059 決定 1: 下のプロジェクトで足した休日は、そのプロジェクトのタスクだけ止まり、時間はほかへ回る
    sub = 11
    tasks = [
        _task(1, remaining=16, project_id=sub, due_date=date(2026, 11, 3)),
        _task(2, remaining=8, due_date=date(2026, 11, 30)),
    ]
    seats = {(ALICE, PROJECT): _seat(8)}
    result = CompletionForecaster(today=MONDAY).forecast(
        tasks=tasks,
        board=TaskProgressBoard(tasks, {}),
        dependencies=(),
        seats=seats,
        root_of=lambda project_id: PROJECT,
        project_days_off=lambda project_id: frozenset({date(2026, 11, 3)}) if project_id == sub else frozenset(),
    )
    assert result.task(2).finish == date(2026, 11, 3)  # 火は 1 が休みなので 2 へ
    assert result.task(1).finish == date(2026, 11, 4)  # 月・(火は下のプロジェクトの休日)・水


def test_weekend_is_skipped_and_workdays_follow_the_team() -> None:
    result = _forecast([_task(1, remaining=48)], {(ALICE, PROJECT): _seat()})
    assert result.task(1).finish == date(2026, 11, 9)  # 月〜金の 5 日 + 次の月
    six_days = [Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY, Weekday.SATURDAY]
    result = _forecast([_task(1, remaining=48)], {(ALICE, PROJECT): _seat(workdays=six_days)})
    assert result.task(1).finish == date(2026, 11, 7)


def test_seats_are_separate_per_project() -> None:
    other = 20
    tasks = [_task(1, remaining=8), _task(2, remaining=8, project_id=other)]
    seats = {(ALICE, PROJECT): _seat(8, 50), (ALICE, other): _seat(8, 50)}
    result = _forecast(tasks, seats)
    assert result.task(1).finish == date(2026, 11, 3)
    assert result.task(2).finish == date(2026, 11, 3)


# ---- 順番と比率 --------------------------------------------------------------


def test_tasks_of_one_person_are_done_in_order_of_due_then_priority() -> None:
    tasks = [
        _task(1, remaining=8, due_date=date(2026, 11, 20)),
        _task(2, remaining=8, due_date=date(2026, 11, 10)),
        _task(3, remaining=8, priority=5),
        _task(4, remaining=8, priority=1),
    ]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    assert result.task(2).finish == date(2026, 11, 2)
    assert result.task(1).finish == date(2026, 11, 3)
    assert result.task(3).finish == date(2026, 11, 4)
    assert result.task(4).finish == date(2026, 11, 5)


def test_leftover_of_a_finished_task_goes_to_the_next_on_the_same_day() -> None:
    tasks = [_task(1, remaining=3, due_date=date(2026, 11, 2)), _task(2, remaining=5)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    assert result.task(1).finish == MONDAY
    assert (result.task(2).start, result.task(2).finish) == (MONDAY, MONDAY)


def test_allocation_does_not_go_faster_when_the_person_is_free() -> None:
    # 比率 25% は 2 時間/日。ほかに仕事が無くても速くならない
    result = _forecast([_task(1, remaining=4, allocation_percent=25)], {(ALICE, PROJECT): _seat()})
    assert result.task(1).finish == date(2026, 11, 3)


def test_allocations_over_100_percent_are_scaled_down() -> None:
    tasks = [_task(1, remaining=8, allocation_percent=100), _task(2, remaining=8, allocation_percent=100)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    assert result.task(1).finish == date(2026, 11, 3)
    assert result.task(2).finish == date(2026, 11, 3)


def test_planned_start_date_is_respected() -> None:
    task = _task(1, remaining=8, start_date=date(2026, 11, 4))
    result = _forecast([task], {(ALICE, PROJECT): _seat()})
    assert (result.task(1).start, result.task(1).finish) == (date(2026, 11, 4), date(2026, 11, 4))


def test_a_waiting_task_is_skipped_and_the_next_one_goes_first() -> None:
    tasks = [
        _task(1, BOB, 16),
        _task(2, ALICE, 8, due_date=date(2026, 11, 2)),  # 期限は早いが BOB の 1 を待つ
        _task(3, ALICE, 8),
    ]
    seats = {(ALICE, PROJECT): _seat(), (BOB, PROJECT): _seat()}
    result = _forecast(tasks, seats, [_fs(1, 2)])
    assert result.task(3).finish == MONDAY
    assert result.task(2).finish == date(2026, 11, 4)
    assert result.task(2).overdue_days == 2


# ---- 依存 ----------------------------------------------------------------


def test_fs_lag_counts_calendar_days() -> None:
    tasks = [_task(1, ALICE, 8), _task(2, BOB, 8)]
    seats = {(ALICE, PROJECT): _seat(), (BOB, PROJECT): _seat()}
    result = _forecast(tasks, seats, [_fs(1, 2, lag=2)])
    assert result.task(2).start == date(2026, 11, 5)  # 月の翌日 + 2 日 = 木


def test_ss_starts_on_the_same_day_as_the_predecessor() -> None:
    tasks = [_task(1, ALICE, 16, start_date=date(2026, 11, 3)), _task(2, BOB, 8)]
    seats = {(ALICE, PROJECT): _seat(), (BOB, PROJECT): _seat()}
    result = _forecast(tasks, seats, [_fs(1, 2, kind=DependencyType.SS)])
    assert result.task(2).start == date(2026, 11, 3)


def test_ff_holds_the_finish_until_the_predecessor_finishes() -> None:
    tasks = [_task(1, ALICE, 24), _task(2, BOB, 4)]
    seats = {(ALICE, PROJECT): _seat(), (BOB, PROJECT): _seat()}
    result = _forecast(tasks, seats, [_fs(1, 2, kind=DependencyType.FF)])
    assert result.task(2).start == MONDAY
    assert result.task(2).finish == date(2026, 11, 4)


def test_finished_predecessor_does_not_hold_the_successor() -> None:
    tasks = [_task(1, status=TaskStatus.DONE), _task(2, remaining=8)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()}, [_fs(1, 2)])
    assert result.task(2).finish == MONDAY


def test_successor_of_an_unforecast_task_waits() -> None:
    tasks = [_task(1, assignee=None), _task(2, remaining=8), _task(3, remaining=8)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()}, [_fs(1, 2), _fs(2, 3)])
    assert result.task(2).gap is ForecastGap.WAITING
    assert result.task(3).gap is ForecastGap.WAITING


def test_cycle_waits() -> None:
    tasks = [_task(1), _task(2)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()}, [_fs(1, 2), _fs(2, 1)], horizon_days=30)
    assert result.task(1).gap is ForecastGap.WAITING
    assert result.task(2).gap is ForecastGap.WAITING


# ---- 子を持つタスクとマイルストーン ---------------------------------------------------


def test_parent_rolls_up_its_leaves() -> None:
    tasks = [
        _task(1, remaining=None, estimated_hours=Decimal("100"), due_date=date(2026, 11, 3)),
        _task(2, remaining=8, parent_task_id=1),
        _task(3, remaining=8, parent_task_id=1, due_date=date(2026, 11, 2)),
        _task(4, status=TaskStatus.DONE, parent_task_id=1),
    ]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    parent = result.task(1)
    assert (parent.start, parent.finish) == (MONDAY, date(2026, 11, 3))
    assert parent.overdue_days == 0  # 親自身の見積 100h は数えない


def test_parent_with_an_unforecast_leaf_gets_no_forecast() -> None:
    tasks = [_task(1, remaining=None), _task(2, parent_task_id=1), _task(3, assignee=None, parent_task_id=1)]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()})
    assert result.task(1).gap is ForecastGap.CHILD_UNFORECAST


def test_dependency_on_a_parent_waits_for_all_its_leaves() -> None:
    tasks = [_task(1, remaining=None), _task(2, ALICE, 8, parent_task_id=1), _task(3, ALICE, 16, parent_task_id=1),
             _task(4, BOB, 8)]
    seats = {(ALICE, PROJECT): _seat(), (BOB, PROJECT): _seat()}
    result = _forecast(tasks, seats, [_fs(1, 4)])
    assert result.task(4).start == date(2026, 11, 5)


def test_milestone_counts_unforecast_tasks_and_overdue() -> None:
    milestone = Milestone(id=9, user_id=ALICE, name="M", due_date=date(2026, 11, 2))
    tasks = [
        _task(1, remaining=16, milestone_id=9),
        _task(2, assignee=None, milestone_id=9),
        _task(3, status=TaskStatus.DONE, milestone_id=9),
    ]
    result = _forecast(tasks, {(ALICE, PROJECT): _seat()}).milestone(milestone)
    assert result.finish == date(2026, 11, 3)
    assert result.unforecast_count == 1
    assert result.overdue_days == 1
