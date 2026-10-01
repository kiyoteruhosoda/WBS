"""親タスクの進捗は全子孫の実績と残を合計してから同じ式に通す（ADR-0010）。"""

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
    # 親 1 ─ 子 2（実績 6・残 2）
    #      └ 子 3 ─ 孫 4（実績 2・見積 10 → 残 8）
    #              └ 孫 5（実績 4・残 手で 0）
    parent = _task(1, estimated_hours=Decimal("100"))  # 親自身の見積は数えない
    tasks = [
        parent,
        _task(2, parent_task_id=1, remaining_hours=Decimal("2")),
        _task(3, parent_task_id=1, estimated_hours=Decimal("50")),  # 中間の見積も数えない
        _task(4, parent_task_id=3, estimated_hours=Decimal("10")),
        _task(5, parent_task_id=3, remaining_hours=Decimal("0")),
    ]
    board = TaskProgressBoard(tasks, {1: 1.0, 2: 6.0, 3: 1.0, 4: 2.0, 5: 4.0})

    figures = board.figures(parent)
    # 実績は親・中間も含めて全部: 1 + 6 + 1 + 2 + 4 = 14、残は葉だけ: 2 + 8 + 0 = 10
    assert figures.actual_hours == 14.0
    assert figures.remaining_hours == 10.0
    assert board.progress_percent(parent) == round(14 / 24 * 100, 1)
    # 中間（3）も自分の子孫で積み上げる: 実績 1 + 2 + 4 = 7、残 8 + 0 = 8
    assert board.progress_percent(tasks[2]) == round(7 / 15 * 100, 1)


def test_parent_is_not_stuck_at_100_when_a_child_overruns() -> None:
    # 子が見積 5h に対して 8h 使い、残を 2h と見直した。親は 8 / (8 + 2 + 5) で 100% にならない
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
    # 輪の中では葉が無いので残は決まらない。止まることだけを見る
    assert board.progress_percent(a) is None
