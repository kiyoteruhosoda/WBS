from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.milestone import Milestone


class MilestoneRepository(ABC):
    @abstractmethod
    def find_by_id(self, milestone_id: int) -> Milestone | None: ...
    @abstractmethod
    def find_all(self, user_id: int) -> list[Milestone]: ...
    @abstractmethod
    def save(self, milestone: Milestone) -> Milestone: ...
    @abstractmethod
    def soft_delete(self, milestone_id: int) -> None: ...
