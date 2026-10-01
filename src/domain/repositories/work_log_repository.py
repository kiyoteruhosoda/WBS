from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

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
    @abstractmethod
    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[WorkLog]:
        """利用者の実績（削除していないもの）を日付の順に。``first_day``〜``last_day`` は両端を含む。

        ⚠ 数えるのは**本人が書いた、本人のタスクの**実績だけ（他人のタスクに付いた行は出さない）。
        消したタスクの実績は出す（実績そのものは残っているため）。
        """
