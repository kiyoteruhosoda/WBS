"""取り込んだカレンダーの読み込みの状態と回の保存先（SQLAlchemy）。ADR-0037。

⚠ ``save`` / ``replace`` / ``delete`` は flush までで commit しない（確定はユースケースの ``UnitOfWork``）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from sqlalchemy import and_, delete, insert, or_, select
from sqlalchemy.orm import Session

from src.domain.entities.calendar_import import CalendarImport, FeedSubscription, ImportSource
from src.domain.repositories.calendar_import_repository import (
    CalendarImportRepository,
    ImportedOccurrenceRepository,
)
from src.domain.value_objects.imported_occurrence import ImportedOccurrence
from src.infrastructure.database.models import CalendarImportModel, ImportedOccurrenceModel

_INSERT_BATCH = 500


class SqlAlchemyCalendarImportRepository(CalendarImportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, calendar_id: int) -> CalendarImport | None:
        model = self._session.get(CalendarImportModel, calendar_id)
        return _calendar_import(model) if model is not None else None

    def find_many(self, calendar_ids: Iterable[int]) -> list[CalendarImport]:
        ids = list(calendar_ids)
        if not ids:
            return []
        stmt = select(CalendarImportModel).where(CalendarImportModel.calendar_id.in_(ids))
        return [_calendar_import(m) for m in self._session.scalars(stmt)]

    def find_subscribed(self) -> list[CalendarImport]:
        stmt = (
            select(CalendarImportModel)
            .where(CalendarImportModel.feed_url_sealed.is_not(None))
            .order_by(CalendarImportModel.calendar_id)
        )
        return [_calendar_import(m) for m in self._session.scalars(stmt)]

    def save(self, calendar_import: CalendarImport) -> CalendarImport:
        model = self._session.get(CalendarImportModel, calendar_import.calendar_id)
        if model is None:
            model = CalendarImportModel(calendar_id=calendar_import.calendar_id)
            self._session.add(model)
        subscription = calendar_import.subscription
        model.source = calendar_import.source.value
        model.imported_at = calendar_import.imported_at
        model.event_count = calendar_import.event_count
        model.feed_url_sealed = subscription.sealed_url if subscription else None
        model.feed_url_hint = subscription.url_hint if subscription else None
        model.last_attempt_at = calendar_import.last_attempt_at
        model.last_error = calendar_import.last_error
        self._session.flush()
        return calendar_import

    def delete(self, calendar_id: int) -> None:
        self._session.execute(
            delete(CalendarImportModel).where(CalendarImportModel.calendar_id == calendar_id)
        )
        self._session.flush()


class SqlAlchemyImportedOccurrenceRepository(ImportedOccurrenceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace(self, calendar_id: int, occurrences: Sequence[ImportedOccurrence]) -> None:
        self.delete_all(calendar_id)
        rows = [
            {
                "calendar_id": calendar_id,
                "title": o.title,
                "location": o.location,
                "start_utc": o.start_utc,
                "end_utc": o.end_utc,
                "start_date": o.start_date,
                "end_date": o.end_date,
            }
            for o in occurrences
        ]
        for begin in range(0, len(rows), _INSERT_BATCH):
            self._session.execute(insert(ImportedOccurrenceModel), rows[begin : begin + _INSERT_BATCH])
        self._session.flush()

    def find(
        self,
        calendar_ids: Iterable[int],
        *,
        from_utc: datetime,
        to_utc: datetime,
        from_date: date,
        to_date: date,
    ) -> list[tuple[int, ImportedOccurrence]]:
        ids = list(calendar_ids)
        if not ids:
            return []
        m = ImportedOccurrenceModel
        stmt = (
            select(m)
            .where(m.calendar_id.in_(ids))
            .where(
                or_(
                    # 時刻のある回: [from_utc, to_utc) に掛かる（長さ 0 の回は開始が中にあれば）
                    and_(
                        m.start_utc.is_not(None),
                        m.start_utc < to_utc,
                        or_(m.end_utc > from_utc, m.start_utc >= from_utc),
                    ),
                    # 終日の回: [from_date, to_date] の日に掛かる（終わりの日は含まない）
                    and_(m.start_date.is_not(None), m.start_date <= to_date, m.end_date > from_date),
                )
            )
            .order_by(m.id)
        )
        return [(row.calendar_id, _occurrence(row)) for row in self._session.scalars(stmt)]

    def delete_all(self, calendar_id: int) -> None:
        self._session.execute(
            delete(ImportedOccurrenceModel).where(ImportedOccurrenceModel.calendar_id == calendar_id)
        )
        self._session.flush()


def _calendar_import(model: CalendarImportModel) -> CalendarImport:
    subscription = (
        FeedSubscription(sealed_url=model.feed_url_sealed, url_hint=model.feed_url_hint or "")
        if model.feed_url_sealed is not None
        else None
    )
    return CalendarImport(
        calendar_id=model.calendar_id,
        source=ImportSource(model.source),
        imported_at=model.imported_at,
        event_count=model.event_count,
        subscription=subscription,
        last_attempt_at=model.last_attempt_at,
        last_error=model.last_error,
    )


def _occurrence(model: ImportedOccurrenceModel) -> ImportedOccurrence:
    return ImportedOccurrence(
        title=model.title,
        location=model.location,
        start_utc=model.start_utc,
        end_utc=model.end_utc,
        start_date=model.start_date,
        end_date=model.end_date,
    )


__all__ = ["SqlAlchemyCalendarImportRepository", "SqlAlchemyImportedOccurrenceRepository"]
