"""Receive time closed in Tracker (task #540 / ADR-0056).

- Replace: per Tracker closing period (user x first day), retire the previously received rows and insert the sent rows.
  Also retire WBS's own closing rows for the same period (from before moving to Tracker) (Tracker ADR-0053 decision 4; no double counting)
- Revoke: when the closing is reopened in Tracker, retire that period's rows

Retiring is a soft delete (``deleted_at``). Rows for tasks missing from or deleted in WBS are not accepted; their ids are returned.

Both record the calling app and the operation in ``machine_operation_logs`` in the same transaction (task #802 / ADR-0068).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ValidationError
from src.domain.value_objects.work_log_source import WorkLogSource
from src.infrastructure.database.models import MachineOperationLogModel
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository
from src.shared.clock import utcnow

HOURS_QUANTUM = Decimal("0.01")


def hours_of(seconds: int) -> Decimal:
    """The value stored in ``work_logs.hours`` (2 decimals; the exact length is ``duration_seconds``)."""
    return (Decimal(seconds) / Decimal(3600)).quantize(HOURS_QUANTUM, rounding=ROUND_HALF_UP)

#: Upper limit of rows accepted per period (every day x tasks; periods are at most a month)
MAX_ENTRIES = 5000


@dataclass(frozen=True)
class ClosedTimeEntry:
    wbs_task_id: int
    work_date: date
    seconds: int


@dataclass(frozen=True)
class ClosedTimeReceipt:
    #: Number of rows inserted
    stored: int
    #: Tasks missing from or deleted in WBS (not accepted)
    unknown_task_ids: list[int]


class TrackerClosedTimeUseCases:
    def __init__(self, session: Session, *, client_id: str) -> None:
        self._session = session
        self._client_id = client_id
        self._tasks = SqlAlchemyTaskRepository(session)
        self._work_logs = SqlAlchemyWorkLogRepository(session)

    def replace(
        self, user_id: int, first_day: date, last_day: date, entries: list[ClosedTimeEntry]
    ) -> ClosedTimeReceipt:
        if last_day < first_day:
            raise ValidationError("last_day must be on or after first_day")
        if len(entries) > MAX_ENTRIES:
            raise ValidationError(f"at most {MAX_ENTRIES} entries per period")
        totals: dict[tuple[int, date], int] = defaultdict(int)
        for entry in entries:
            if not first_day <= entry.work_date <= last_day:
                raise ValidationError("every entry must fall inside the period")
            if entry.seconds < 0:
                raise ValidationError("seconds must not be negative")
            totals[(entry.wbs_task_id, entry.work_date)] += entry.seconds
        known: dict[int, bool] = {}
        for task_id, _ in totals:
            if task_id not in known:
                known[task_id] = self._tasks.find_by_id(task_id) is not None

        self._work_logs.remove_tracker_period(user_id, first_day)
        self._work_logs.retire_own_closings(user_id, first_day, last_day)
        stored = 0
        for (task_id, day), seconds in sorted(totals.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if seconds <= 0 or not known[task_id]:
                continue
            self._work_logs.save(
                WorkLog(
                    id=None,
                    user_id=user_id,
                    task_id=task_id,
                    work_date=day,
                    hours=hours_of(seconds),
                    source=WorkLogSource.TRACKER,
                    duration_seconds=seconds,
                    tracker_first_day=first_day,
                )
            )
            stored += 1
        self._log_operation(
            user_id, "PUT /api/machine/closed-periods/{first_day}", f"first_day={first_day} stored={stored}"
        )
        self._session.commit()
        return ClosedTimeReceipt(
            stored=stored, unknown_task_ids=sorted(t for t, ok in known.items() if not ok)
        )

    def remove(self, user_id: int, first_day: date) -> int:
        removed = self._work_logs.remove_tracker_period(user_id, first_day)
        self._log_operation(
            user_id, "DELETE /api/machine/closed-periods/{first_day}", f"first_day={first_day} removed={removed}"
        )
        self._session.commit()
        return removed

    def _log_operation(self, user_id: int, operation: str, detail: str) -> None:
        self._session.add(
            MachineOperationLogModel(
                occurred_at=utcnow(),
                client_id=self._client_id,
                user_id=user_id,
                operation=operation,
                detail=detail,
            )
        )


__all__ = [
    "ClosedTimeEntry",
    "ClosedTimeReceipt",
    "TrackerClosedTimeUseCases",
]
