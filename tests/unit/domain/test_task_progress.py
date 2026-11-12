"""Progress = actual / (actual + remaining) (design doc §5.1, ADR-0010)."""

from decimal import Decimal

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus
from src.domain.value_objects.work_figures import WorkFigures


def _task(**kwargs) -> Task:
    defaults = {"id": 1, "user_id": 1, "title": "t"}
    defaults.update(kwargs)
    return Task(**defaults)


def test_progress_is_unknown_without_estimate_or_remaining() -> None:
    # With neither remaining nor estimate there is nothing to judge by (the screen shows "—")
    assert _task().progress_percent(0.0) is None
    assert _task().progress_percent(4.0) is None


def test_progress_done_is_always_100() -> None:
    task = _task(status=TaskStatus.DONE, estimated_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 100.0
    assert _task(status=TaskStatus.DONE).progress_percent(0.0) == 100.0


def test_progress_is_actual_over_actual_plus_remaining() -> None:
    # Example from the design doc: actual 20h, remaining 10h -> 66.7%
    task = _task(estimated_hours=Decimal("25"), remaining_hours=Decimal("10"))
    assert task.progress_percent(20.0) == 66.7


def test_progress_with_default_remaining_matches_estimate_while_within_it() -> None:
    # When remaining is empty, use estimate - actual. Within the estimate this equals actual / estimate
    task = _task(estimated_hours=Decimal("10"))
    assert task.progress_percent(4.0) == 40.0
    assert task.progress_percent(5.5) == 55.0


def test_overrun_task_does_not_stick_to_100_once_remaining_is_entered() -> None:
    # Actual 8h against an estimate of 5h. Revised to remaining 2h gives 8 / (8 + 2) = 80%
    task = _task(estimated_hours=Decimal("5"), remaining_hours=Decimal("2"))
    assert task.progress_percent(8.0) == 80.0


def test_zero_denominator_is_unknown() -> None:
    # Actual 0 and remaining 0 (estimate 0, or not started with remaining entered as 0) gives denominator 0 -> null
    assert _task(estimated_hours=Decimal("0")).progress_percent(0.0) is None
    assert _task(remaining_hours=Decimal("0")).progress_percent(0.0) is None


def test_entered_remaining_wins_over_the_default() -> None:
    task = _task(estimated_hours=Decimal("10"), remaining_hours=Decimal("3"))
    assert task.remaining_hours_from(4.0) == 3.0
    assert task.progress_percent(4.0) == round(4 / 7 * 100, 1)


def test_remaining_defaults_to_estimate_minus_actual() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.remaining_hours_from(0.0) == 10.0
    assert task.remaining_hours_from(4.0) == 6.0


def test_default_remaining_does_not_go_negative() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.remaining_hours_from(12.0) == 0.0


def test_remaining_is_none_without_estimate_or_entry() -> None:
    assert _task().remaining_hours_from(4.0) is None


def test_remaining_is_zero_when_done_even_if_entered() -> None:
    task = _task(status=TaskStatus.DONE, estimated_hours=Decimal("10"), remaining_hours=Decimal("4"))
    assert task.remaining_hours_from(2.0) == 0.0


def test_work_figures_formula() -> None:
    assert WorkFigures(20.0, 10.0).progress_percent(done=False) == 66.7
    assert WorkFigures(0.0, 0.0).progress_percent(done=False) is None
    assert WorkFigures(3.0, None).progress_percent(done=False) is None
    assert WorkFigures(0.0, 0.0).progress_percent(done=True) == 100.0
