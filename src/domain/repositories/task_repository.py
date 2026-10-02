from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.task import Task


class TaskRepository(ABC):
    @abstractmethod
    def find_by_id(self, task_id: int) -> Task | None: ...
    @abstractmethod
    def find_by_id_for_user(self, task_id: int, user_id: int) -> Task | None: ...
    @abstractmethod
    def find_all(self, user_id: int, filters: dict) -> list[Task]:
        """消していないタスク。``filters`` の ``project_ids``（この中のどれかに属する）・
        ``unclassified``（プロジェクトが空）でも絞れる。"""
    @abstractmethod
    def save(self, task: Task) -> Task: ...
    @abstractmethod
    def soft_delete(self, task_id: int, user_id: int | None = None) -> None: ...
    @abstractmethod
    def get_actual_hours(self, task_id: int) -> float: ...
    @abstractmethod
    def get_actual_hours_by_task(self, user_id: int) -> dict[int, float]:
        """利用者のタスクごとの実績（削除していない work_logs の合計）。work_logs の無いタスクは載らない。"""
    @abstractmethod
    def subtree_ids(self, user_id: int, task_id: int) -> list[int]:
        """自分と子孫のタスクの id（消したものも含む。再帰 CTE で 1 回に引く）。"""
    @abstractmethod
    def set_project(self, task_ids: list[int], project_id: int | None) -> None:
        """タスクをまとめて別のプロジェクトへ移す（子孫を親に揃えるため）。"""
    @abstractmethod
    def detach_milestone(self, task_ids: list[int]) -> None:
        """マイルストーンを外す（届かないプロジェクトへ移ったタスク。ADR-0024）。"""
