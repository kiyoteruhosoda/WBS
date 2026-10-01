from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.work_log import WorkLog


class WorkLogRepository(ABC):
    @abstractmethod
    def find_by_id(self, work_log_id: int) -> WorkLog | None: ...
    @abstractmethod
    def find_by_task(self, task_id: int) -> list[WorkLog]: ...
    @abstractmethod
    def save(self, work_log: WorkLog) -> WorkLog: ...
    @abstractmethod
    def soft_delete(self, work_log_id: int) -> None: ...
    @abstractmethod
    def find_by_closing_period(self, closing_period_id: int) -> list[WorkLog]:
        """締めでその期間から作った実績（日付・タスクの順）。"""
    @abstractmethod
    def delete_by_closing_period(self, closing_period_id: int) -> int:
        """締めでその期間から作った実績を消す（物理削除。打刻から作り直せるため）。消した数を返す。"""
