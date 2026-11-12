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
        """Soft-delete the rows received from Tracker for that period (ADR-0056). Returns the number deleted."""

    @abstractmethod
    def retire_own_closings(self, user_id: int, first_day: date, last_day: date) -> int:
        """Soft-delete rows made by WBS's own closing (``source=closing``, from before the move to Tracker) that fall in the period.

        When Tracker sends the same period, Tracker's rows win (Tracker ADR-0053 decision 4). They are set aside to avoid double counting.
        """

    @abstractmethod
    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[WorkLog]:
        """The user's actuals (not deleted) in date order. ``first_day``–``last_day`` are inclusive.

        ⚠ Only actuals **written by the user on the user's own tasks** are counted (rows on other people's tasks are excluded).
        Actuals of deleted tasks are included (the actuals themselves remain).
        """
