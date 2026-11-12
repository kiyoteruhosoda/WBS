"""Find tasks whose remaining work should be reviewed (task #162 / ADR-0017; the "review remaining" mark of ADR-0010).

Remaining is never reduced automatically (it is fixed by hand). Right after a closing adds actuals, tasks whose remaining
looks doubtful as a current estimate are listed with a reason, and the user re-enters it on the spot.

Targets are **unfinished leaves** (DONE, CANCELLED and tasks with children are excluded; a parent's remaining is the roll-up of its children
and is not entered by hand. ADR-0010). Reasons:

| Reason | Condition |
|---|---|
| ``over_estimate`` | Actuals exceed the estimate and no remaining was entered by hand (the default remaining is 0, showing 100%) |
| ``no_remaining`` | Remaining is 0 but the task is unfinished (0 entered by hand, or the estimate used up exactly) |
| ``unknown_remaining`` | There are actuals but neither estimate nor remaining (progress cannot be computed) |
| ``stale_remaining`` | Remaining was entered by hand, actuals grew in the most recently confirmed period, and the task was not edited after that confirmation |

Editing the task (entering remaining, marking it done) puts ``updated_at`` after the confirmation, and the reason goes away.
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
    """Reasons ``task``'s remaining should be reviewed (empty if none).

    ``latest_closed_hours`` is the actuals added to this task in the most recently confirmed closing period;
    ``latest_closed_at`` is the instant of that confirmation (naive UTC; None if no period has been confirmed).
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
