from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.project_work_log import ProjectWorkLog


class ProjectWorkLogRepository(ABC):
    @abstractmethod
    def save(self, log: ProjectWorkLog) -> ProjectWorkLog: ...

    @abstractmethod
    def remove_tracker_period(self, user_id: int, first_day: date) -> int:
        """Tracker から受け取ったその期間の行を論理削除する（ADR-0064）。消した数を返す。"""

    @abstractmethod
    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[ProjectWorkLog]:
        """利用者の、自分に見えるプロジェクトの行（削除していないもの）を日付の順に。両端を含む。"""


__all__ = ["ProjectWorkLogRepository"]
