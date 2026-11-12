"""A parent task's progress sums the actuals and remaining hours of all descendants, then applies the same formula (ADR-0010)."""

from decimal import Decimal

from src.domain.entities.task import Task
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.task_status import TaskStatus


def _task(task_id: int, **kwargs) -> Task:
    return Task(id=task_id, user_id=1, title=f"t{task_id}", **kwargs)


def test_leaf_uses_its_own_figures() -> None:
    leaf = _task(1, estimated_hours=Decimal("10"))
    board = TaskProgressBoard([leaf], {1: 4.0})
    assert not board.has_subtasks(1)
    assert board.progress_percent(leaf) == 40.0


def test_parent_rolls_up_all_descendants() -> None:
    # parent 1 - child 2 (actual 6, remaining 2)
    #          - child 3 - grandchild 4 (actual 2, estimate 10 -> remaining 8)
    #                    - grandchild 5 (actual 4, remaining set to 0 by hand)
    parent = _task(1, estimated_hours=Decimal("100"))  # the parent's own estimate is not counted
    tasks = [
        parent,
        _task(2, parent_task_id=1, remaining_hours=Decimal("2")),
        _task(3, parent_task_id=1, estimated_hours=Decimal("50")),  # nor is the intermediate's estimate
        _task(4, parent_task_id=3, estimated_hours=Decimal("10")),
        _task(5, parent_task_id=3, remaining_hours=Decimal("0")),
    ]
    board = TaskProgressBoard(tasks, {1: 1.0, 2: 6.0, 3: 1.0, 4: 2.0, 5: 4.0})

    figures = board.figures(parent)
    # Actuals include the parent and intermediates: 1 + 6 + 1 + 2 + 4 = 14; remaining is leaves only: 2 + 8 + 0 = 10
    assert figures.actual_hours == 14.0
    assert figures.remaining_hours == 10.0
    assert board.progress_percent(parent) == round(14 / 24 * 100, 1)
    # The intermediate (3) also rolls up its own descendants: actual 1 + 2 + 4 = 7, remaining 8 + 0 = 8
    assert board.progress_percent(tasks[2]) == round(7 / 15 * 100, 1)


def test_parent_is_not_stuck_at_100_when_a_child_overruns() -> None:
    # The child used 8h against a 5h estimate and remaining was revised to 2h. The parent is 8 / (8 + 2 + 5), not 100%
    parent = _task(1)
    tasks = [
        parent,
        _task(2, parent_task_id=1, estimated_hours=Decimal("5"), remaining_hours=Decimal("2")),
        _task(3, parent_task_id=1, estimated_hours=Decimal("5")),
    ]
    board = TaskProgressBoard(tasks, {2: 8.0})
    assert board.progress_percent(parent) == round(8 / 15 * 100, 1)


def test_cancelled_leaf_counts_actual_but_no_remaining() -> None:
    parent = _task(1)
    tasks = [
        parent,
        _task(2, parent_task_id=1, estimated_hours=Decimal("10"), status=TaskStatus.CANCELLED),
        _task(3, parent_task_id=1, estimated_hours=Decimal("4")),
    ]
    board = TaskProgressBoard(tasks, {2: 2.0, 3: 2.0})
    assert board.figures(parent).remaining_hours == 2.0
    assert board.progress_percent(parent) == round(4 / 6 * 100, 1)


def test_parent_with_zero_denominator_is_unknown() -> None:
    parent = _task(1)
    tasks = [parent, _task(2, parent_task_id=1, estimated_hours=Decimal("0"))]
    board = TaskProgressBoard(tasks, {})
    assert board.progress_percent(parent) is None


def test_parent_is_unknown_when_no_leaf_has_remaining() -> None:
    parent = _task(1)
    tasks = [parent, _task(2, parent_task_id=1), _task(3, parent_task_id=1)]
    board = TaskProgressBoard(tasks, {2: 3.0})
    assert board.figures(parent).remaining_hours is None
    assert board.progress_percent(parent) is None


def test_done_parent_is_100() -> None:
    parent = _task(1, status=TaskStatus.DONE)
    tasks = [parent, _task(2, parent_task_id=1, estimated_hours=Decimal("10"))]
    board = TaskProgressBoard(tasks, {})
    assert board.progress_percent(parent) == 100.0


def test_parent_cycle_does_not_loop_forever() -> None:
    a = _task(1, parent_task_id=2, estimated_hours=Decimal("4"))
    b = _task(2, parent_task_id=1, estimated_hours=Decimal("4"))
    board = TaskProgressBoard([a, b], {1: 1.0, 2: 1.0})
    # Inside a cycle there are no leaves, so remaining is undefined. Only check that it terminates
    assert board.progress_percent(a) is None
