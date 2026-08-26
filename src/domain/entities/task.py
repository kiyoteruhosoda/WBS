from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.task_status import TaskStatus
from src.shared.clock import utcnow


@dataclass
class Task:
    id: int | None
    user_id: int
    title: str
    category_id: int | None = None
    priority: int = 3
    urgency: int = 3
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def change_status(self, new_status: TaskStatus, changed_at: datetime | None = None) -> None:
        """Apply the task status state machine and its domain side effects."""
        if self.status == new_status:
            return

        if not self.status.can_transition_to(new_status):
            raise InvalidStatusTransitionError(self.status.value, new_status.value)

        if new_status == TaskStatus.DONE:
            self.completed_at = changed_at or utcnow()
        elif self.status == TaskStatus.DONE:
            self.completed_at = None

        self.status = new_status

    def progress_percent(self, actual_hours: float) -> float:
        # 進捗は「実績時間 ÷ 見積時間」で算出する（見積が未入力なら判断材料がないため 0%）
        if self.status == TaskStatus.DONE:
            return 100.0
        if self.estimated_hours is None or float(self.estimated_hours) <= 0:
            return 0.0
        ratio = min(actual_hours / float(self.estimated_hours), 1.0)
        return round(ratio * 100, 1)

    def remaining_hours_from(self, actual_hours: float) -> float | None:
        # 残り時間は直接入力せず「見積時間 − 実績時間」から常に導出する
        if self.status == TaskStatus.DONE:
            return 0.0
        if self.estimated_hours is None:
            return None
        return round(max(float(self.estimated_hours) - actual_hours, 0.0), 2)

    def priority_score(self, today: date) -> int:
        overdue_days = self._overdue_days(today)
        return self.priority * 100 + self.urgency * 80 + min(overdue_days, 7) * 100

    def _overdue_days(self, today: date) -> int:
        if self.due_date is None or self.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            return 0
        return max((today - self.due_date).days, 0)
