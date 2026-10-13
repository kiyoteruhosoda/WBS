"""タスクを消す・アーカイブする（task #388 / ADR-0046。画面の言葉は #394 で「アーカイブ」）。

打刻や確定した実績（``work_logs``）のあるタスクを消すと、締めた期間の数字や実績の表から名前が消える。
なので**打刻も実績も無いタスクだけを消し**、あるタスクは消さずに**アーカイブする**（一覧と付け替え先に出ない。
実績と締めの表には名前ごと残る）。アーカイブしたタスクを指す WinTrack の規則は止まる（PC へ渡さない。ADR-0043）。

どちらも、いま計測中のタスクには行わない（409）。子タスクは今までどおり残る（親を消しても子は消えない）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.application.dto.task_removal_dto import TaskRemovalAction, TaskRemovalPreview
from src.application.ports.unit_of_work import UnitOfWork
from src.domain.entities.task import Task
from src.domain.exceptions import ConflictError, NotFoundError
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.repositories.tracking_rule_repository import TrackingRuleRepository
from src.shared.clock import utcnow


class TaskRemovalUseCases:
    def __init__(
        self,
        tasks: TaskRepository,
        time_entries: TimeEntryRepository,
        tracking_rules: TrackingRuleRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._tasks = tasks
        self._entries = time_entries
        self._rules = tracking_rules
        self._uow = unit_of_work
        self._now = now

    def preview(self, task_id: int, user_id: int) -> TaskRemovalPreview:
        """消すとどうなるか（確認の窓に出す）。"""
        task = self._owned(task_id, user_id)
        now = self._now()
        entries = self._entries.find_by_task(user_id, task_id)
        rules = [r for r in self._rules.find_all(user_id) if r.task_id == task_id]
        work_log_hours = self._tasks.get_actual_hours(task_id)
        blocked_by: str | None = None
        if any(e.is_running for e in entries):
            blocked_by = "running"
        return TaskRemovalPreview(
            task_id=task_id,
            title=task.title,
            action=(
                TaskRemovalAction.ARCHIVE
                if entries or work_log_hours > 0
                else TaskRemovalAction.DELETE
            ),
            time_entries=len(entries),
            tracked_seconds=sum(int(e.duration(now).total_seconds()) for e in entries),
            work_log_hours=work_log_hours,
            tracking_rules=len(rules),
            blocked_by=blocked_by,
            archived=task.is_archived,
        )

    def delete(self, task_id: int, user_id: int) -> None:
        """打刻も実績も無いタスクを消す。あれば 409（アーカイブする）。"""
        preview = self._removable(task_id, user_id)
        if preview.action is not TaskRemovalAction.DELETE:
            raise ConflictError(
                "the task has time entries or work logs; archive it instead of deleting it"
            )
        self._tasks.soft_delete(task_id, user_id)
        self._uow.commit()

    def archive(self, task_id: int, user_id: int) -> None:
        """アーカイブする（冪等）。打刻や実績が無いタスクもアーカイブできる。"""
        self._removable(task_id, user_id)
        task = self._owned(task_id, user_id)
        task.archive(self._now())
        self._tasks.save(task)
        self._uow.commit()

    def _removable(self, task_id: int, user_id: int) -> TaskRemovalPreview:
        preview = self.preview(task_id, user_id)
        if preview.blocked_by == "running":
            raise ConflictError("the task is being timed; stop the timer first")
        return preview

    def _owned(self, task_id: int, user_id: int) -> Task:
        task = self._tasks.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task
