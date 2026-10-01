from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.domain.entities.occurrence_completion import OccurrenceCompletion


class OccurrenceCompletionRepository(ABC):
    """回の済み（ADR-0025）。持ち主は予定で決まる（呼び出し側が予定の持ち主を確かめてから使う）。

    ⚠ 書き込みは flush までで、確定はユースケースの ``UnitOfWork.commit()``。
    """

    @abstractmethod
    def find_by_events(self, event_ids: Iterable[int]) -> list[OccurrenceCompletion]:
        """予定（複数）の済みの回。"""

    @abstractmethod
    def replace_for_event(self, event_id: int, completions: Iterable[OccurrenceCompletion]) -> None:
        """その予定の済みを、渡したものだけにする（同じ鍵が重なれば先のものを残す）。"""
