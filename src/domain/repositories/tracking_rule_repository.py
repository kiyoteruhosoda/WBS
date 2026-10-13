from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.tracking_rule import TrackingRule


class TrackingRuleRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def find_by_id(self, rule_id: int) -> TrackingRule | None: ...

    @abstractmethod
    def find_all(self, user_id: int) -> list[TrackingRule]:
        """利用者の規則を ``position``（同じなら id）の順に。"""

    @abstractmethod
    def save(self, rule: TrackingRule) -> TrackingRule: ...

    @abstractmethod
    def delete(self, rule_id: int) -> None: ...

    @abstractmethod
    def last_changed_at(self, user_id: int) -> datetime | None:
        """規則を最後に作った・直した・消した・並べ替えた時刻（一度も無ければ None）。"""

    @abstractmethod
    def mark_changed(self, user_id: int, at: datetime) -> None:
        """規則を変えたことを記す（消したときも ``last_changed_at`` が進むように）。"""

    @abstractmethod
    def last_task_change_at(self, user_id: int) -> datetime | None:
        """規則の行き先のタスクを最後に変えた（直した・閉じた・消した）時刻。消したタスクも数える。"""
