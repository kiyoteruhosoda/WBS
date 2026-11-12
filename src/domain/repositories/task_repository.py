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
        """Tasks that are not deleted. Can also be filtered by ``filters``' ``project_ids`` (belongs to any of them),
        ``unclassified`` (no project), ``assignee_user_id`` (assignee) and
        ``unassigned`` (no assignee). ⚠ "The user's" means "visible to the user" (ADR-0055)."""
    @abstractmethod
    def save(self, task: Task) -> Task: ...
    @abstractmethod
    def soft_delete(self, task_id: int, user_id: int | None = None) -> None: ...
    @abstractmethod
    def get_actual_hours(self, task_id: int) -> float: ...
    @abstractmethod
    def get_actual_hours_by_task(self, user_id: int) -> dict[int, float]:
        """Actuals per task visible to the user (sum of everyone's non-deleted work_logs). Tasks without work_logs are not included."""
    @abstractmethod
    def subtree_ids(self, user_id: int, task_id: int) -> list[int]:
        """Ids of the task and its descendants (including deleted ones; fetched at once with a recursive CTE)."""
    @abstractmethod
    def set_project(self, task_ids: list[int], project_id: int | None) -> None:
        """Move tasks to another project in bulk (to align descendants with their parent)."""
    @abstractmethod
    def detach_milestone(self, task_ids: list[int]) -> None:
        """Detach the milestone (tasks moved to a project it cannot reach. ADR-0024)."""
