from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from src.domain.exceptions import DomainError


class TaskStatus(StrEnum):
    TODO = "TODO"
    DOING = "DOING"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {TaskStatus.DOING, TaskStatus.CANCELLED},
    TaskStatus.DOING: {TaskStatus.DONE, TaskStatus.WAITING},
    TaskStatus.WAITING: {TaskStatus.DOING},
    TaskStatus.DONE: {TaskStatus.TODO, TaskStatus.DOING, TaskStatus.WAITING, TaskStatus.CANCELLED},
    TaskStatus.CANCELLED: {TaskStatus.TODO},
}


@dataclass(slots=True)
class Task:
    title: str
    user_id: int = 1
    priority: int = 3
    urgency: int = 3
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    remaining_hours: float | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainError("タスクタイトルは必須です。")
        if not 1 <= self.priority <= 5 or not 1 <= self.urgency <= 5:
            raise DomainError("優先度と緊急度は 1〜5 で指定してください。")
        if self.start_date and self.due_date and self.start_date > self.due_date:
            raise DomainError("開始日は期限以前である必要があります。")

    def transition_to(self, next_status: TaskStatus, now: datetime) -> None:
        if next_status == self.status:
            return
        if next_status not in _ALLOWED[self.status]:
            raise DomainError(f"{self.status} から {next_status} へは遷移できません。")
        old = self.status
        self.status = next_status
        if next_status is TaskStatus.DONE:
            self.completed_at = now
            self.remaining_hours = 0
        elif old is TaskStatus.DONE:
            self.completed_at = None
