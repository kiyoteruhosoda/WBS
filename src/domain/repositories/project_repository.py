from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.project import Project


class ProjectRepository(ABC):
    @abstractmethod
    def find_by_id(self, project_id: int) -> Project | None: ...
    @abstractmethod
    def find_by_id_for_user(self, project_id: int, user_id: int) -> Project | None:
        """Return it if visible to the user (members of the root also see descendants. ADR-0055)."""
    @abstractmethod
    def find_all(self, user_id: int) -> list[Project]:
        """All projects visible to the user (parents and children alike, ordered by sibling order → id)."""
    @abstractmethod
    def subtree_ids(self, user_id: int, project_id: int) -> list[int]:
        """Ids of the project and its descendants (fetched at once with a recursive CTE). Empty if the project is not visible."""
    @abstractmethod
    def save(self, project: Project) -> Project: ...
    @abstractmethod
    def set_sort_orders(self, ordered_ids: list[int]) -> None:
        """Renumber siblings from 0 in the given order."""
    @abstractmethod
    def delete(self, project_id: int) -> None:
        """Delete the row (the caller checks that it is empty)."""
    @abstractmethod
    def has_contents(self, project_id: int) -> bool:
        """Whether it has any child project, non-deleted task or non-deleted milestone."""
