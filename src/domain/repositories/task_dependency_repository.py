from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.task_dependency import TaskDependency


class TaskDependencyRepository(ABC):
    """Dependencies between tasks.

    ``task_dependencies`` has no owner column, so **reads must always go through a method that filters by user**.
    Only dependencies whose both end tasks belong to that user are returned (the owner is found via the tasks).
    There is deliberately no method that fetches everyone's — with one, other people's dependencies would mix in once there are two users.
    """

    @abstractmethod
    def find_by_task_for_user(self, task_id: int, user_id: int) -> list[TaskDependency]:
        """Dependencies where ``task_id`` is either predecessor or successor and both ends belong to ``user_id``."""

    @abstractmethod
    def find_all_for_user(self, user_id: int) -> list[TaskDependency]:
        """All dependencies whose both end tasks belong to ``user_id``."""

    @abstractmethod
    def save(self, dep: TaskDependency) -> TaskDependency:
        """Add one (if the same pair exists, overwrite its type and lag). Commits."""

    @abstractmethod
    def delete(self, predecessor_id: int, successor_id: int) -> None:
        """Delete one. Does nothing if absent. Commits."""
