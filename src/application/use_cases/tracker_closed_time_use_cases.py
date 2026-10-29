"""Tracker で締めた時間を受け取る（task #540 / ADR-0056）。

- 置き換え: Tracker の締めの期間（利用者 × 初日）ごとに、前に受け取った行を退けて送られた行で入れ直す。
  同じ期間の WBS 自身の締めの行（Tracker へ移る前のもの）も退ける（Tracker の ADR-0053 決定 4。二重に数えない）
- 取り消し: Tracker で締めを開け直したら、その期間の行を退ける

退けるのは論理削除（``deleted_at``）。WBS に無い・消したタスクの行は受け取らず、id を返す。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.application.use_cases.closing_use_cases import hours_of
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ValidationError
from src.domain.value_objects.work_log_source import WorkLogSource
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository

#: 1 期間に受け取る行の上限（毎日 × タスク。区切りは月まで）
MAX_ENTRIES = 5000


@dataclass(frozen=True)
class ClosedTimeEntry:
    wbs_task_id: int
    work_date: date
    seconds: int


@dataclass(frozen=True)
class ClosedTimeReceipt:
    #: 入れた行の数
    stored: int
    #: WBS に無い・消したタスク（受け取らなかった）
    unknown_task_ids: list[int]


class TrackerClosedTimeUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
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
        self._session.commit()
        return ClosedTimeReceipt(
            stored=stored, unknown_task_ids=sorted(t for t, ok in known.items() if not ok)
        )

    def remove(self, user_id: int, first_day: date) -> int:
        removed = self._work_logs.remove_tracker_period(user_id, first_day)
        self._session.commit()
        return removed


__all__ = [
    "ClosedTimeEntry",
    "ClosedTimeReceipt",
    "TrackerClosedTimeUseCases",
]
