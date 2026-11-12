from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.milestone import Milestone


class MilestoneRepository(ABC):
    @abstractmethod
    def find_by_id(self, milestone_id: int) -> Milestone | None: ...
    @abstractmethod
    def find_by_id_for_user(self, milestone_id: int, user_id: int) -> Milestone | None:
        """Return it if not deleted and visible to the user (ADR-0055)."""
    @abstractmethod
    def find_all(
        self,
        user_id: int,
        *,
        project_ids: list[int] | None = None,
        unclassified: bool = False,
    ) -> list[Milestone]:
        """Milestones that are not deleted and visible to the user. Can be narrowed to those in any of ``project_ids`` or to unclassified only."""
    @abstractmethod
    def save(self, milestone: Milestone) -> Milestone: ...
    @abstractmethod
    def soft_delete(self, milestone_id: int) -> None: ...
