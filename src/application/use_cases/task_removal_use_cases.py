"""Delete or archive tasks (task #388 / ADR-0046; the on-screen word became "archive" in #394).

Deleting a task that has confirmed actuals (``work_logs``) makes its name disappear from the actuals tables.
So **only tasks without actuals are deleted**; tasks with actuals are **archived** instead (hidden from lists and reassignment targets,
but kept with their name in the actuals tables). Child tasks stay as before (deleting the parent does not delete children).

Time punch and WinTrack rules moved to Tracker, so they are not checked here (task #543 / ADR-0070).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.application.dto.task_removal_dto import TaskRemovalAction, TaskRemovalPreview
from src.application.ports.unit_of_work import UnitOfWork
from src.domain.entities.task import Task
from src.domain.exceptions import ConflictError, NotFoundError
from src.domain.repositories.task_repository import TaskRepository
from src.shared.clock import utcnow


class TaskRemovalUseCases:
    def __init__(
        self,
        tasks: TaskRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._tasks = tasks
        self._uow = unit_of_work
        self._now = now

    def preview(self, task_id: int, user_id: int) -> TaskRemovalPreview:
        """What happens when deleting (shown in the confirmation dialog)."""
        task = self._owned(task_id, user_id)
        work_log_hours = self._tasks.get_actual_hours(task_id)
        return TaskRemovalPreview(
            task_id=task_id,
            title=task.title,
            action=(
                TaskRemovalAction.ARCHIVE if work_log_hours > 0 else TaskRemovalAction.DELETE
            ),
            work_log_hours=work_log_hours,
            archived=task.is_archived,
        )

    def delete(self, task_id: int, user_id: int) -> None:
        """Delete a task without actuals. 409 if it has some (archive it instead)."""
        preview = self.preview(task_id, user_id)
        if preview.action is not TaskRemovalAction.DELETE:
            raise ConflictError("the task has work logs; archive it instead of deleting it")
        self._tasks.soft_delete(task_id, user_id)
        self._uow.commit()

    def archive(self, task_id: int, user_id: int) -> None:
        """Archive (idempotent). Tasks without actuals can be archived too."""
        task = self._owned(task_id, user_id)
        task.archive(self._now())
        self._tasks.save(task)
        self._uow.commit()

    def _owned(self, task_id: int, user_id: int) -> Task:
        task = self._tasks.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task
