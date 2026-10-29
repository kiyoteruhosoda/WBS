"""Tracker で締めた時間を受け取る（task #540 / ADR-0056、プロジェクトだけの時間は task #708 / ADR-0064）。

- 置き換え: Tracker の締めの期間（利用者 × 初日）ごとに、前に受け取った行を退けて送られた行で入れ直す。
  同じ期間の WBS 自身の締めの行（Tracker へ移る前のもの）も退ける（Tracker の ADR-0053 決定 4。二重に数えない）
- 取り消し: Tracker で締めを開け直したら、その期間の行を退ける

行は WBS のタスク（``work_logs``）か、タスクに結ばない WBS のプロジェクト（``project_work_logs``）のどちらか。
退けるのは論理削除（``deleted_at``）。WBS に無い・消したタスク、無い・本人に見えないプロジェクトの行は受け取らず、id を返す。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.application.use_cases.closing_use_cases import hours_of
from src.domain.entities.project_work_log import ProjectWorkLog
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ValidationError
from src.domain.value_objects.work_log_source import WorkLogSource
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.project_work_log_repository import (
    SqlAlchemyProjectWorkLogRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository

#: 1 期間に受け取る行の上限（毎日 × タスク。区切りは月まで）
MAX_ENTRIES = 5000


@dataclass(frozen=True)
class ClosedTimeEntry:
    """1 行。``wbs_task_id`` か ``wbs_project_id`` のどちらか 1 つを持つ（タスクがあればタスクだけ）。"""

    wbs_task_id: int | None
    work_date: date
    seconds: int
    wbs_project_id: int | None = None


@dataclass(frozen=True)
class ClosedTimeReceipt:
    #: 入れた行の数
    stored: int
    #: WBS に無い・消したタスク（受け取らなかった）
    unknown_task_ids: list[int]
    #: WBS に無い・本人に見えないプロジェクト（受け取らなかった）
    unknown_project_ids: list[int]


class TrackerClosedTimeUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._tasks = SqlAlchemyTaskRepository(session)
        self._work_logs = SqlAlchemyWorkLogRepository(session)
        self._projects = SqlAlchemyProjectRepository(session)
        self._project_logs = SqlAlchemyProjectWorkLogRepository(session)

    def replace(
        self, user_id: int, first_day: date, last_day: date, entries: list[ClosedTimeEntry]
    ) -> ClosedTimeReceipt:
        if last_day < first_day:
            raise ValidationError("last_day must be on or after first_day")
        if len(entries) > MAX_ENTRIES:
            raise ValidationError(f"at most {MAX_ENTRIES} entries per period")
        totals: dict[tuple[int, date], int] = defaultdict(int)
        project_totals: dict[tuple[int, date], int] = defaultdict(int)
        for entry in entries:
            if not first_day <= entry.work_date <= last_day:
                raise ValidationError("every entry must fall inside the period")
            if entry.seconds < 0:
                raise ValidationError("seconds must not be negative")
            if (entry.wbs_task_id is None) == (entry.wbs_project_id is None):
                raise ValidationError("every entry needs exactly one of wbs_task_id or wbs_project_id")
            if entry.wbs_task_id is not None:
                totals[(entry.wbs_task_id, entry.work_date)] += entry.seconds
            elif entry.wbs_project_id is not None:
                project_totals[(entry.wbs_project_id, entry.work_date)] += entry.seconds
        known: dict[int, bool] = {}
        for task_id, _ in totals:
            if task_id not in known:
                known[task_id] = self._tasks.find_by_id(task_id) is not None
        # プロジェクトは本人に見えるものだけ（タスクと違い、だれのプロジェクトかで工数の行き先が決まる）
        known_projects: dict[int, bool] = {}
        for project_id, _ in project_totals:
            if project_id not in known_projects:
                known_projects[project_id] = (
                    self._projects.find_by_id_for_user(project_id, user_id) is not None
                )

        self._work_logs.remove_tracker_period(user_id, first_day)
        self._project_logs.remove_tracker_period(user_id, first_day)
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
        for (project_id, day), seconds in sorted(
            project_totals.items(), key=lambda kv: (kv[0][1], kv[0][0])
        ):
            if seconds <= 0 or not known_projects[project_id]:
                continue
            self._project_logs.save(
                ProjectWorkLog(
                    id=None,
                    user_id=user_id,
                    project_id=project_id,
                    work_date=day,
                    seconds=seconds,
                    tracker_first_day=first_day,
                )
            )
            stored += 1
        self._session.commit()
        return ClosedTimeReceipt(
            stored=stored,
            unknown_task_ids=sorted(t for t, ok in known.items() if not ok),
            unknown_project_ids=sorted(p for p, ok in known_projects.items() if not ok),
        )

    def remove(self, user_id: int, first_day: date) -> int:
        removed = self._work_logs.remove_tracker_period(user_id, first_day)
        removed += self._project_logs.remove_tracker_period(user_id, first_day)
        self._session.commit()
        return removed


__all__ = [
    "ClosedTimeEntry",
    "ClosedTimeReceipt",
    "TrackerClosedTimeUseCases",
]
