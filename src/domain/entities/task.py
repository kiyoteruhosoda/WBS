from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.task_status import TaskStatus


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
    remaining_hours: Decimal | None = None
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
            self.completed_at = changed_at or datetime.utcnow()
            self.remaining_hours = Decimal("0")
        elif self.status == TaskStatus.DONE:
            self.completed_at = None

        self.status = new_status

    def progress_percent(self, actual_hours: float) -> float:
        if self.status == TaskStatus.DONE:
            return 100.0

        remaining = float(self.remaining_hours) if self.remaining_hours is not None else 0.0
        # 作業ログがなくても、見積時間より残り時間が少なければその差を消化済みとみなす
        # （タスク作成時に見積・残りを入力しただけでも進捗に反映される）。
        # 残り時間が未入力の場合は消化済みと推定しない（見積のみで100%になるのを防ぐ）
        implied_hours = 0.0
        if self.estimated_hours is not None and self.remaining_hours is not None:
            implied_hours = max(float(self.estimated_hours) - remaining, 0.0)
        effective_actual = max(actual_hours, implied_hours)
        total = effective_actual + remaining
        if total <= 0:
            return 0.0
        return round(effective_actual / total * 100, 1)

    def priority_score(self, today: date) -> int:
        overdue_days = self._overdue_days(today)
        return self.priority * 100 + self.urgency * 80 + min(overdue_days, 7) * 100

    def _overdue_days(self, today: date) -> int:
        if self.due_date is None or self.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            return 0
        return max((today - self.due_date).days, 0)
