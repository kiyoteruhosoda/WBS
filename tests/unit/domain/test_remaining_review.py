"""残を見直してほしいタスクの理由（task #162 / ADR-0017）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.domain.entities.task import Task
from src.domain.services.remaining_review import RemainingReviewReason, remaining_review_reasons
from src.domain.value_objects.task_status import TaskStatus

CLOSED_AT = datetime(2026, 9, 16, 1, 0)


def _task(**fields) -> Task:
    return Task(id=1, user_id=1, title="設計", **fields)


def _reasons(task: Task, actual: float, *, closed_hours: float = 0.0, has_subtasks: bool = False):
    return remaining_review_reasons(
        task,
        actual_hours=actual,
        has_subtasks=has_subtasks,
        latest_closed_hours=closed_hours,
        latest_closed_at=CLOSED_AT,
    )


def test_over_the_estimate_without_a_remaining_is_asked() -> None:
    assert _reasons(_task(estimated_hours=Decimal("2")), 3) == [RemainingReviewReason.OVER_ESTIMATE]


def test_an_estimate_used_up_exactly_shows_no_remaining() -> None:
    assert _reasons(_task(estimated_hours=Decimal("2")), 2) == [RemainingReviewReason.NO_REMAINING]


def test_an_untouched_estimate_is_not_asked() -> None:
    assert _reasons(_task(estimated_hours=Decimal("2")), 0) == []
    assert _reasons(_task(estimated_hours=Decimal("2")), 1) == []


def test_work_without_estimate_or_remaining_is_asked() -> None:
    assert _reasons(_task(), 1) == [RemainingReviewReason.UNKNOWN_REMAINING]
    assert _reasons(_task(), 0) == []


def test_an_entered_zero_on_an_open_task_is_asked() -> None:
    assert _reasons(_task(remaining_hours=Decimal("0")), 0) == [RemainingReviewReason.NO_REMAINING]


def test_an_entered_remaining_left_untouched_after_closing_is_asked() -> None:
    before = _task(remaining_hours=Decimal("4"), updated_at=datetime(2026, 9, 1))
    after = _task(remaining_hours=Decimal("4"), updated_at=datetime(2026, 9, 17))

    assert _reasons(before, 5, closed_hours=2) == [RemainingReviewReason.STALE_REMAINING]
    assert _reasons(before, 5, closed_hours=0) == []
    assert _reasons(after, 5, closed_hours=2) == []
    # 確定した期間が無ければ聞かない
    assert (
        remaining_review_reasons(
            before, actual_hours=5, has_subtasks=False, latest_closed_hours=2, latest_closed_at=None
        )
        == []
    )


def test_finished_and_parent_tasks_are_never_asked() -> None:
    assert _reasons(_task(estimated_hours=Decimal("1"), status=TaskStatus.DONE), 3) == []
    assert _reasons(_task(estimated_hours=Decimal("1"), status=TaskStatus.CANCELLED), 3) == []
    assert _reasons(_task(estimated_hours=Decimal("1")), 3, has_subtasks=True) == []
