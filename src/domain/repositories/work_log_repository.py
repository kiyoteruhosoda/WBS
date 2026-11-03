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
    def remove_tracker_period(self, user_id: int, first_day: date) -> int:
        """Tracker から受け取ったその期間の行を論理削除する（ADR-0056）。消した数を返す。"""

    @abstractmethod
    def retire_own_closings(self, user_id: int, first_day: date, last_day: date) -> int:
        """WBS 自身の締めで作った行（``source=closing``。Tracker へ移る前のもの）のうち、期間に入るものを論理削除する。

        Tracker が同じ期間を送ってきたら、そちらが正（Tracker の ADR-0053 決定 4）。二重に数えないために退ける。
        """

    @abstractmethod
    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[WorkLog]:
        """利用者の実績（削除していないもの）を日付の順に。``first_day``〜``last_day`` は両端を含む。

        ⚠ 数えるのは**本人が書いた、本人のタスクの**実績だけ（他人のタスクに付いた行は出さない）。
        消したタスクの実績は出す（実績そのものは残っているため）。
        """
