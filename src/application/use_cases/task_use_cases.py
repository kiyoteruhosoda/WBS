from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.domain.entities.task import Task
from src.domain.exceptions import NotFoundError, InvalidStatusTransitionError
from src.domain.repositories.task_repository import TaskRepository
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository

VALID_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.TODO: [TaskStatus.DOING, TaskStatus.CANCELLED],
    TaskStatus.DOING: [TaskStatus.DONE, TaskStatus.WAITING],
    TaskStatus.WAITING: [TaskStatus.DOING],
    TaskStatus.DONE: [TaskStatus.TODO, TaskStatus.DOING, TaskStatus.WAITING],
    TaskStatus.CANCELLED: [TaskStatus.TODO],
}


def _compute_progress(actual: float, remaining: Decimal | None, status: TaskStatus) -> float:
    if status == TaskStatus.DONE:
        return 100.0
    remaining_f = float(remaining) if remaining is not None else 0.0
    if actual == 0 and remaining_f == 0:
        return 0.0
    total = actual + remaining_f
    if total == 0:
        return 0.0
    return round(actual / total * 100, 1)


class TaskUseCases:
    def __init__(self, session: Session) -> None:
        self._repo: TaskRepository = SqlAlchemyTaskRepository(session)
        self._session = session

    def list_tasks(self, user_id: int, filters: dict) -> list[dict]:
        tasks = self._repo.find_all(user_id, filters)
        return [self._enrich(t) for t in tasks]

    def get_task(self, task_id: int) -> dict:
        task = self._repo.find_by_id(task_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return self._enrich(task)

    def create_task(self, dto: CreateTaskDTO) -> dict:
        task = Task(
            id=None,
            user_id=dto.user_id,
            title=dto.title,
            category_id=dto.category_id,
            priority=dto.priority,
            urgency=dto.urgency,
            status=dto.status,
            start_date=dto.start_date,
            due_date=dto.due_date,
            estimated_hours=dto.estimated_hours,
            remaining_hours=dto.remaining_hours,
            memo=dto.memo,
            parent_task_id=dto.parent_task_id,
            milestone_id=dto.milestone_id,
        )
        saved = self._repo.save(task)
        self._session.commit()
        return self._enrich(saved)

    def update_task(self, task_id: int, dto: UpdateTaskDTO) -> dict:
        task = self._repo.find_by_id(task_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        if dto.title is not None:
            task.title = dto.title
        if dto.category_id is not None:
            task.category_id = dto.category_id
        if dto.priority is not None:
            task.priority = dto.priority
        if dto.urgency is not None:
            task.urgency = dto.urgency
        if dto.status is not None:
            self._apply_status_transition(task, dto.status)
        if dto.start_date is not None:
            task.start_date = dto.start_date
        if dto.due_date is not None:
            task.due_date = dto.due_date
        if dto.estimated_hours is not None:
            task.estimated_hours = dto.estimated_hours
        if dto.remaining_hours is not None:
            task.remaining_hours = dto.remaining_hours
        if dto.memo is not None:
            task.memo = dto.memo
        if dto.parent_task_id is not None:
            task.parent_task_id = dto.parent_task_id
        if dto.milestone_id is not None:
            task.milestone_id = dto.milestone_id
        saved = self._repo.save(task)
        self._session.commit()
        return self._enrich(saved)

    def delete_task(self, task_id: int) -> None:
        task = self._repo.find_by_id(task_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        self._repo.soft_delete(task_id)
        self._session.commit()

    def _apply_status_transition(self, task: Task, new_status: TaskStatus) -> None:
        if task.status == new_status:
            return
        allowed = VALID_TRANSITIONS.get(task.status, [])
        if new_status not in allowed:
            raise InvalidStatusTransitionError(task.status.value, new_status.value)
        if new_status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()
            task.remaining_hours = Decimal("0")
        elif task.status == TaskStatus.DONE:
            task.completed_at = None
        task.status = new_status

    def _enrich(self, task: Task) -> dict:
        actual = self._repo.get_actual_hours(task.id)
        today = date.today()
        overdue_days = max((today - task.due_date).days, 0) if task.due_date and task.status not in (TaskStatus.DONE, TaskStatus.CANCELLED) else 0
        priority_score = task.priority * 100 + task.urgency * 80 + min(overdue_days, 7) * 100
        progress = _compute_progress(actual, task.remaining_hours, task.status)
        return {
            "id": task.id,
            "user_id": task.user_id,
            "title": task.title,
            "category_id": task.category_id,
            "priority": task.priority,
            "urgency": task.urgency,
            "status": task.status.value,
            "start_date": task.start_date,
            "due_date": task.due_date,
            "estimated_hours": float(task.estimated_hours) if task.estimated_hours is not None else None,
            "remaining_hours": float(task.remaining_hours) if task.remaining_hours is not None else None,
            "actual_hours": actual,
            "progress_percent": progress,
            "priority_score": priority_score,
            "memo": task.memo,
            "parent_task_id": task.parent_task_id,
            "milestone_id": task.milestone_id,
            "completed_at": task.completed_at,
            "deleted_at": task.deleted_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
