from decimal import Decimal

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus


def _task(**kwargs) -> Task:
    defaults = {"id": 1, "user_id": 1, "title": "t"}
    defaults.update(kwargs)
    return Task(**defaults)


def test_progress_zero_without_estimate() -> None:
    # 見積が未入力なら実績があっても進捗は算出しない
    assert _task().progress_percent(0.0) == 0.0
    assert _task().progress_percent(4.0) == 0.0


def test_progress_done_is_always_100() -> None:
    task = _task(status=TaskStatus.DONE, estimated_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 100.0


def test_progress_is_actual_over_estimate() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 0.0
    assert task.progress_percent(4.0) == 40.0
    assert task.progress_percent(5.5) == 55.0


def test_progress_caps_at_100_when_actual_exceeds_estimate() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.progress_percent(12.0) == 100.0


def test_remaining_is_estimate_minus_actual() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.remaining_hours_from(0.0) == 10.0
    assert task.remaining_hours_from(4.0) == 6.0


def test_remaining_does_not_go_negative() -> None:
    task = _task(estimated_hours=Decimal("10"))
    assert task.remaining_hours_from(12.0) == 0.0


def test_remaining_is_none_without_estimate() -> None:
    assert _task().remaining_hours_from(4.0) is None


def test_remaining_is_zero_when_done() -> None:
    task = _task(status=TaskStatus.DONE, estimated_hours=Decimal("10"))
    assert task.remaining_hours_from(2.0) == 0.0
