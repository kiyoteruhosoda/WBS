from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.value_objects.time_entry_source import TimeEntrySource
from src.infrastructure.database.models import TimeEntryModel
from src.shared.clock import utcnow


class SqlAlchemyTimeEntryRepository(TimeEntryRepository):
    """⚠ ``save`` / ``delete`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。

    切り替え（前を止めて次を始める）は 2 行を書くので、ここで commit すると片方だけ残りうる。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, entry_id: int) -> TimeEntry | None:
        model = self._session.get(TimeEntryModel, entry_id)
        return self._to_entity(model) if model is not None else None

    def find_running(self, user_id: int) -> TimeEntry | None:
        stmt = select(TimeEntryModel).where(
            TimeEntryModel.user_id == user_id,
            TimeEntryModel.ended_at.is_(None),
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model is not None else None

    def find_latest_task_id(self, user_id: int) -> int | None:
        stmt = (
            select(TimeEntryModel.task_id)
            .where(TimeEntryModel.user_id == user_id, TimeEntryModel.task_id.is_not(None))
            .order_by(TimeEntryModel.started_at.desc(), TimeEntryModel.id.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def find_earliest_started_at(self, user_id: int) -> datetime | None:
        stmt = select(func.min(TimeEntryModel.started_at)).where(TimeEntryModel.user_id == user_id)
        return self._session.scalar(stmt)

    def find_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[TimeEntry]:
        # TimeEntry.overlaps と同じ条件（走っている打刻は終わりが無いものとして扱う）
        stmt = (
            select(TimeEntryModel)
            .where(
                TimeEntryModel.user_id == user_id,
                TimeEntryModel.started_at < end,
                or_(
                    TimeEntryModel.ended_at.is_(None),
                    TimeEntryModel.ended_at > start,
                    TimeEntryModel.started_at >= start,
                ),
            )
            .order_by(TimeEntryModel.started_at, TimeEntryModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, entry: TimeEntry) -> TimeEntry:
        if entry.id is None:
            model = TimeEntryModel(
                user_id=entry.user_id,
                task_id=entry.task_id,
                started_at=entry.started_at,
                ended_at=entry.ended_at,
                memo=entry.memo,
                source=entry.source.value,
            )
            self._session.add(model)
        else:
            found = self._session.get(TimeEntryModel, entry.id)
            if found is None:
                raise ValueError(f"TimeEntry {entry.id} not found")
            model = found
            model.task_id = entry.task_id
            model.started_at = entry.started_at
            model.ended_at = entry.ended_at
            model.memo = entry.memo
            model.source = entry.source.value
            model.updated_at = utcnow()
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            if not _is_running_entry_collision(exc):
                raise
            raise ConflictError("A time entry is already running for this user") from exc
        return self._to_entity(model)

    def delete(self, entry_id: int) -> None:
        model = self._session.get(TimeEntryModel, entry_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    def _to_entity(self, model: TimeEntryModel) -> TimeEntry:
        return TimeEntry(
            id=model.id,
            user_id=model.user_id,
            task_id=model.task_id,
            started_at=model.started_at,
            ended_at=model.ended_at,
            memo=model.memo,
            source=TimeEntrySource(model.source),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def _is_running_entry_collision(exc: IntegrityError) -> bool:
    """部分一意索引 ``uq_time_entries_running_per_user`` に当たったか（同時の Start など）。

    SQLite の文言は ``UNIQUE constraint failed: time_entries.user_id``。
    """
    message = str(exc.orig)
    return "uq_time_entries_running_per_user" in message or "time_entries.user_id" in message
