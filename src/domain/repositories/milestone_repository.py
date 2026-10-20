from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.milestone import Milestone


class MilestoneRepository(ABC):
    @abstractmethod
    def find_by_id(self, milestone_id: int) -> Milestone | None: ...
    @abstractmethod
    def find_by_id_for_user(self, milestone_id: int, user_id: int) -> Milestone | None:
        """消しておらず、利用者に見えるなら返す（ADR-0055）。"""
    @abstractmethod
    def find_all(
        self,
        user_id: int,
        *,
        project_ids: list[int] | None = None,
        unclassified: bool = False,
    ) -> list[Milestone]:
        """消しておらず、利用者に見えるマイルストーン。``project_ids`` の中のどれかに属するもの・未分類だけにも絞れる。"""
    @abstractmethod
    def save(self, milestone: Milestone) -> Milestone: ...
    @abstractmethod
    def soft_delete(self, milestone_id: int) -> None: ...
