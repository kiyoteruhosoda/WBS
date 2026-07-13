from __future__ import annotations

import enum


class TaskStatus(enum.StrEnum):
    TODO = "TODO"
    DOING = "DOING"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]

    def can_transition_to(self, next_status: TaskStatus) -> bool:
        return next_status in self.allowed_next_statuses()

    def allowed_next_statuses(self) -> frozenset[TaskStatus]:
        transitions: dict[TaskStatus, frozenset[TaskStatus]] = {
            TaskStatus.TODO: frozenset({TaskStatus.DOING, TaskStatus.CANCELLED}),
            TaskStatus.DOING: frozenset({TaskStatus.DONE, TaskStatus.WAITING}),
            TaskStatus.WAITING: frozenset({TaskStatus.DOING}),
            TaskStatus.DONE: frozenset({TaskStatus.TODO, TaskStatus.DOING, TaskStatus.WAITING}),
            TaskStatus.CANCELLED: frozenset({TaskStatus.TODO}),
        }
        return transitions[self]
