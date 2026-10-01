from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.task import Task


class TaskRepository(ABC):
    @abstractmethod
    def find_by_id(self, task_id: int) -> Task | None: ...
    @abstractmethod
    def find_by_id_for_user(self, task_id: int, user_id: int) -> Task | None: ...
    @abstractmethod
    def find_all(self, user_id: int, filters: dict) -> list[Task]: ...
    @abstractmethod
    def save(self, task: Task) -> Task: ...
    @abstractmethod
    def soft_delete(self, task_id: int, user_id: int | None = None) -> None: ...
    @abstractmethod
    def get_actual_hours(self, task_id: int) -> float: ...
    @abstractmethod
    def get_actual_hours_by_task(self, user_id: int) -> dict[int, float]:
        """利用者のタスクごとの実績（削除していない work_logs の合計）。work_logs の無いタスクは載らない。"""
