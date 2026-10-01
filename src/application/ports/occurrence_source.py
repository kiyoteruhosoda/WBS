"""予定の回を期間で引く口（締めの画面・「予定の回をそのまま打刻にする」、ADR-0012）。

``CalendarEventUseCases`` がそのままこの形を満たす。打刻・締めのユースケースが予定の
リポジトリ・展開の仕組みに直接依存しないよう、使う 1 つだけを切り出す。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.application.dto.calendar_event_dto import OccurrenceView


class OccurrenceSource(Protocol):
    def list_occurrence_views(
        self, user_id: int, from_date: date, to_date: date, viewer_time_zone: str
    ) -> list[OccurrenceView]: ...


class NoOccurrences:
    """予定を繋がない試験のための既定（回は 1 つも無い）。"""

    def list_occurrence_views(
        self, user_id: int, from_date: date, to_date: date, viewer_time_zone: str
    ) -> list[OccurrenceView]:
        return []
