from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.project_member import ProjectMember


class ProjectMemberRepository(ABC):
    @abstractmethod
    def find_by_project(self, project_id: int) -> list[ProjectMember]:
        """Members of that (root) project (in the order added)."""

    @abstractmethod
    def find_by_user(self, user_id: int) -> list[ProjectMember]:
        """Root rows the person is a member of."""

    @abstractmethod
    def find(self, project_id: int, user_id: int) -> ProjectMember | None: ...

    @abstractmethod
    def save(self, member: ProjectMember) -> ProjectMember:
        """Add (no id) or overwrite role, hours per day and allocation."""

    @abstractmethod
    def delete(self, project_id: int, user_id: int) -> None: ...

    @abstractmethod
    def delete_all(self, project_id: int) -> None:
        """Delete all rows of that project (when it stops being a root or is deleted)."""
