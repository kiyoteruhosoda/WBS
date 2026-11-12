from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskRemovalAction(StrEnum):
    DELETE = "delete"
    """No confirmed actuals: delete."""
    ARCHIVE = "archive"
    """Has confirmed actuals: archive instead of deleting."""


@dataclass(frozen=True)
class TaskRemovalPreview:
    """What happens when deleting the task (shown in the confirmation dialog, ADR-0046)."""

    task_id: int
    title: str
    action: TaskRemovalAction
    # Total of confirmed actuals (work_logs)
    work_log_hours: float
    archived: bool
