"""残を見直してほしいタスクを見つける（task #162 / ADR-0017、ADR-0010 の「残を見直す」印）。

残は自動で減らさない（手で直す）。締めで実績が入った直後に、残が今の読みとして怪しいものを
理由つきで挙げ、その場で入れ直してもらう。

対象は**未完了の葉**（DONE・CANCELLED・子を持つタスクは外す。親の残は子の積み上げで、
手で入れさせない。ADR-0010）。理由:

| 理由 | 判定 |
|---|---|
| ``over_estimate`` | 見積を超えた実績があり、残を手で入れていない（既定の残が 0 で 100% と出ている） |
| ``no_remaining`` | 残が 0 なのに未完了（手で 0 を入れた、または見積をちょうど使い切った） |
| ``unknown_remaining`` | 見積も残も無いのに実績がある（進捗率が出ない） |
| ``stale_remaining`` | 手で入れた残があり、直近に確定した期間で実績が増えたのに、その確定の後にタスクを直していない |

タスクを直す（残を入れる・完了にする）と、``updated_at`` が確定より後になり、理由は消える。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus


class RemainingReviewReason(StrEnum):
    OVER_ESTIMATE = "over_estimate"
    NO_REMAINING = "no_remaining"
    UNKNOWN_REMAINING = "unknown_remaining"
    STALE_REMAINING = "stale_remaining"


CLOSED_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


def remaining_review_reasons(
    task: Task,
    *,
    actual_hours: float,
    has_subtasks: bool,
    latest_closed_hours: float,
    latest_closed_at: datetime | None,
) -> list[RemainingReviewReason]:
    """``task`` の残を見直してほしい理由（無ければ空）。

    ``latest_closed_hours`` は直近に確定した締めの期間でこのタスクに入った実績、
    ``latest_closed_at`` はその確定の瞬間（naive な UTC。確定した期間が無ければ None）。
    """
    if task.status in CLOSED_STATUSES or has_subtasks:
        return []
    entered = task.remaining_hours
    if entered is None:
        estimate = task.estimated_hours
        if estimate is None:
            return [RemainingReviewReason.UNKNOWN_REMAINING] if actual_hours > 0 else []
        if actual_hours > float(estimate):
            return [RemainingReviewReason.OVER_ESTIMATE]
        if actual_hours > 0 and task.remaining_hours_from(actual_hours) == 0:
            return [RemainingReviewReason.NO_REMAINING]
        return []
    if float(entered) == 0:
        return [RemainingReviewReason.NO_REMAINING]
    if (
        latest_closed_at is not None
        and latest_closed_hours > 0
        and (task.updated_at is None or task.updated_at < latest_closed_at)
    ):
        return [RemainingReviewReason.STALE_REMAINING]
    return []


__all__ = ["CLOSED_STATUSES", "RemainingReviewReason", "remaining_review_reasons"]
