from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.task_dependency import TaskDependency


class TaskDependencyRepository(ABC):
    """タスク間の依存。

    ``task_dependencies`` には持ち主の列が無いので、**読み出しは必ず利用者で絞る口を通す**。
    両端のタスクがどちらもその利用者のものである依存だけを返す（タスクを辿って持ち主を見る）。
    全員分を引く口は置かない ——置くと、利用者が 2 人になった日に他人の依存が混ざる。
    """

    @abstractmethod
    def find_by_task_for_user(self, task_id: int, user_id: int) -> list[TaskDependency]:
        """``task_id`` が先行・後続のどちらかに居る依存のうち、両端とも ``user_id`` のもの。"""

    @abstractmethod
    def find_all_for_user(self, user_id: int) -> list[TaskDependency]:
        """両端とも ``user_id`` のタスクである依存すべて。"""

    @abstractmethod
    def save(self, dep: TaskDependency) -> TaskDependency:
        """足す（同じ組が在れば種別と lag を書き換える）。確定まで行う。"""

    @abstractmethod
    def delete(self, predecessor_id: int, successor_id: int) -> None:
        """消す。無ければ何もしない。確定まで行う。"""
