from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.task_status import TaskStatus
from src.domain.value_objects.work_figures import WorkFigures
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
    # 手で入れた残。空なら「見積 − 実績」を既定に使う（ADR-0010）
    remaining_hours: Decimal | None = None
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # 属するプロジェクト（空 = 未分類）。⚠ 子タスクは親と同じ値（ADR-0024）
    project_id: int | None = None
    # 担当者（空可。根のプロジェクトのメンバー、未分類なら作った人。ADR-0055）
    assignee_user_id: int | None = None
    # アサイン比率（%、空可）。入れたタスクは担当者の 1 日の空きのうちこの割合で毎日進む（ADR-0058）
    allocation_percent: int | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    # アーカイブした時刻（打刻や実績のあるタスクは消さずにアーカイブする。ADR-0046）。一覧・付け替え先に出ない
    archived_at: datetime | None = None
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

    @property
    def is_open(self) -> bool:
        """まだ作業できるか（完了・中止でなく、アーカイブもしていない）。"""
        return self.status not in (TaskStatus.DONE, TaskStatus.CANCELLED) and not self.is_archived

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self, at: datetime) -> None:
        """アーカイブする（冪等）。"""
        if self.archived_at is None:
            self.archived_at = at

    def progress_percent(self, actual_hours: float) -> float | None:
        # 進捗率 = 実績 ÷（実績 ＋ 残）。子を持つタスクの積み上げは TaskProgressBoard が出す
        return self.work_figures(actual_hours).progress_percent(done=self.status == TaskStatus.DONE)

    def work_figures(self, actual_hours: float) -> WorkFigures:
        return WorkFigures(actual_hours=actual_hours, remaining_hours=self.remaining_hours_from(actual_hours))

    def remaining_hours_from(self, actual_hours: float) -> float | None:
        # 残は手で入れた値が優先。空なら「見積 − 実績」（負にしない）を既定にする。DONE は 0
        if self.status == TaskStatus.DONE:
            return 0.0
        if self.remaining_hours is not None:
            return round(float(self.remaining_hours), 2)
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
