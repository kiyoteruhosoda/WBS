from decimal import Decimal

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus


def _task(**kwargs) -> Task:
    defaults = {"id": 1, "user_id": 1, "title": "t"}
    defaults.update(kwargs)
    return Task(**defaults)


def test_progress_zero_without_any_hours() -> None:
    assert _task().progress_percent(0.0) == 0.0


def test_progress_done_is_always_100() -> None:
    task = _task(status=TaskStatus.DONE, estimated_hours=Decimal("10"), remaining_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 100.0


def test_progress_from_worklogs_only() -> None:
    task = _task(remaining_hours=Decimal("6"))
    assert task.progress_percent(4.0) == 40.0


def test_progress_reflects_estimate_minus_remaining_at_creation() -> None:
    # 作成時に見積10h・残り4hを入れた場合、作業ログがなくても60%になる
    task = _task(estimated_hours=Decimal("10"), remaining_hours=Decimal("4"))
    assert task.progress_percent(0.0) == 60.0


def test_progress_uses_larger_of_actual_and_implied() -> None:
    task = _task(estimated_hours=Decimal("10"), remaining_hours=Decimal("4"))
    # 実績8h > 見積差分6h → 実績を採用: 8 / (8 + 4) = 66.7%
    assert task.progress_percent(8.0) == 66.7


def test_progress_remaining_larger_than_estimate_does_not_go_negative() -> None:
    task = _task(estimated_hours=Decimal("4"), remaining_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 0.0


def test_progress_estimate_fully_remaining_is_zero() -> None:
    task = _task(estimated_hours=Decimal("10"), remaining_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 0.0


def test_progress_estimate_without_remaining_stays_zero() -> None:
    # 残り時間が未入力なら見積だけで消化済みと推定しない（100%になるバグの回帰テスト）
    task = _task(estimated_hours=Decimal("10"))
    assert task.progress_percent(0.0) == 0.0
