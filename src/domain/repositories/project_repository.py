from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.project import Project


class ProjectRepository(ABC):
    @abstractmethod
    def find_by_id(self, project_id: int) -> Project | None: ...
    @abstractmethod
    def find_all(self, user_id: int) -> list[Project]:
        """利用者のプロジェクト全部（親子の別なく、兄弟の並び → id の順）。"""
    @abstractmethod
    def subtree_ids(self, user_id: int, project_id: int) -> list[int]:
        """自分と子孫の id（再帰 CTE で 1 回に引く）。他人のプロジェクトなら空。"""
    @abstractmethod
    def save(self, project: Project) -> Project: ...
    @abstractmethod
    def set_sort_orders(self, ordered_ids: list[int]) -> None:
        """兄弟の並びを、渡した順に 0 から振り直す。"""
    @abstractmethod
    def delete(self, project_id: int) -> None:
        """行ごと消す（空であることは呼ぶ側が確かめる）。"""
    @abstractmethod
    def has_contents(self, project_id: int) -> bool:
        """子プロジェクト・消していないタスク・消していないマイルストーンのどれかがあるか。"""
