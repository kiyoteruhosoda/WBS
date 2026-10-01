"""回の済みの保存先（SQLAlchemy）。ADR-0025。

表 ``calendar_event_completions``。回は（候補日, 系列の開始時刻）、単発は両方 NULL。
⚠ 書き込みは flush までで commit しない。確定はユースケースの ``UnitOfWork``。
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.occurrence_completion import OccurrenceCompletion
from src.domain.repositories.occurrence_completion_repository import (
    OccurrenceCompletionRepository,
)
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.infrastructure.database.models import CalendarEventCompletionModel


class SqlAlchemyOccurrenceCompletionRepository(OccurrenceCompletionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_events(self, event_ids: Iterable[int]) -> list[OccurrenceCompletion]:
        ids = sorted(set(event_ids))
        if not ids:
            return []
        stmt = (
            select(CalendarEventCompletionModel)
            .where(CalendarEventCompletionModel.event_id.in_(ids))
            .order_by(CalendarEventCompletionModel.id)
        )
        return [_to_entity(m) for m in self._session.scalars(stmt)]

    def replace_for_event(
        self, event_id: int, completions: Iterable[OccurrenceCompletion]
    ) -> None:
        # ⚠ 同じ鍵を消して入れ直すと一意制約に当たりうるので、先に消して flush してから入れる。
        existing = self._session.scalars(
            select(CalendarEventCompletionModel).where(
                CalendarEventCompletionModel.event_id == event_id
            )
        )
        for model in existing:
            self._session.delete(model)
        self._session.flush()
        seen: set[OccurrenceKey | None] = set()
        for completion in completions:
            if completion.occurrence_key in seen:
                continue
            seen.add(completion.occurrence_key)
            key = completion.occurrence_key
            self._session.add(
                CalendarEventCompletionModel(
                    event_id=event_id,
                    occurrence_date=key.date if key is not None else None,
                    occurrence_time=key.time if key is not None else None,
                    completed_at=completion.completed_at,
                )
            )
        self._session.flush()


def _to_entity(model: CalendarEventCompletionModel) -> OccurrenceCompletion:
    key = (
        OccurrenceKey(model.occurrence_date, model.occurrence_time)
        if model.occurrence_date is not None
        else None
    )
    return OccurrenceCompletion(model.event_id, key, model.completed_at)


__all__ = ["SqlAlchemyOccurrenceCompletionRepository"]
