from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.domain.entities.task import Task
from src.domain.repositories.task_repository import TaskRepository
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.database.models import TaskModel, WorkLogModel
from src.shared.clock import utcnow


class SqlAlchemyTaskRepository(TaskRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, task_id: int) -> Task | None:
        model = self._session.get(TaskModel, task_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    def find_by_id_for_user(self, task_id: int, user_id: int) -> Task | None:
        stmt = select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == user_id,
            TaskModel.deleted_at.is_(None),
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model is not None else None

    def find_all(self, user_id: int, filters: dict) -> list[Task]:
        stmt = select(TaskModel).where(
            TaskModel.user_id == user_id,
            TaskModel.deleted_at.is_(None),
        )
        if "status" in filters and filters["status"]:
            stmt = stmt.where(TaskModel.status == filters["status"])
        if "category_id" in filters and filters["category_id"] is not None:
            stmt = stmt.where(TaskModel.category_id == filters["category_id"])
        if "milestone_id" in filters and filters["milestone_id"] is not None:
            stmt = stmt.where(TaskModel.milestone_id == filters["milestone_id"])
        if "parent_task_id" in filters and filters["parent_task_id"] is not None:
            stmt = stmt.where(TaskModel.parent_task_id == filters["parent_task_id"])
        # プロジェクトの子孫まで含めた id の一覧（呼ぶ側が再帰 CTE で引いて渡す。ADR-0024）
        if filters.get("project_ids") is not None:
            stmt = stmt.where(TaskModel.project_id.in_(filters["project_ids"]))
        if filters.get("unclassified"):
            stmt = stmt.where(TaskModel.project_id.is_(None))
        stmt = stmt.order_by(TaskModel.priority.desc(), TaskModel.urgency.desc(), TaskModel.id)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, task: Task) -> Task:
        if task.id is None:
            model = self._to_model(task)
            self._session.add(model)
            self._session.flush()
            task.id = model.id
            task.created_at = model.created_at
            task.updated_at = model.updated_at
            return task
        else:
            model = self._session.get(TaskModel, task.id)
            if model is None:
                raise ValueError(f"Task {task.id} not found")
            model.title = task.title
            model.category_id = task.category_id
            model.priority = task.priority
            model.urgency = task.urgency
            model.status = task.status.value if isinstance(task.status, TaskStatus) else task.status
            model.start_date = task.start_date
            model.due_date = task.due_date
            model.estimated_hours = task.estimated_hours
            model.remaining_hours = task.remaining_hours
            model.memo = task.memo
            model.parent_task_id = task.parent_task_id
            model.milestone_id = task.milestone_id
            model.project_id = task.project_id
            model.completed_at = task.completed_at
            model.updated_at = utcnow()
            self._session.flush()
            return self._to_entity(model)

    def soft_delete(self, task_id: int, user_id: int | None = None) -> None:
        stmt = select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.deleted_at.is_(None),
        )
        if user_id is not None:
            stmt = stmt.where(TaskModel.user_id == user_id)
        model = self._session.scalar(stmt)
        if model:
            model.deleted_at = utcnow()
            self._session.flush()

    def get_actual_hours(self, task_id: int) -> float:
        result = self._session.execute(
            select(func.sum(WorkLogModel.hours)).where(
                WorkLogModel.task_id == task_id,
                WorkLogModel.deleted_at.is_(None),
            )
        ).scalar()
        return float(result or 0)

    def get_actual_hours_by_task(self, user_id: int) -> dict[int, float]:
        rows = self._session.execute(
            select(WorkLogModel.task_id, func.sum(WorkLogModel.hours))
            .join(TaskModel, TaskModel.id == WorkLogModel.task_id)
            .where(TaskModel.user_id == user_id, WorkLogModel.deleted_at.is_(None))
            .group_by(WorkLogModel.task_id)
        )
        return {task_id: float(total or 0) for task_id, total in rows}

    def subtree_ids(self, user_id: int, task_id: int) -> list[int]:
        # UNION（重複を落とす）なので、親子が万一環になっていても止まる
        base = (
            select(TaskModel.id)
            .where(TaskModel.id == task_id, TaskModel.user_id == user_id)
            .cte("task_subtree", recursive=True)
        )
        child = (
            select(TaskModel.id)
            .join(base, TaskModel.parent_task_id == base.c.id)
            .where(TaskModel.user_id == user_id)
        )
        tree = base.union(child)
        return [int(i) for i in self._session.scalars(select(tree.c.id))]

    def set_project(self, task_ids: list[int], project_id: int | None) -> None:
        if not task_ids:
            return
        self._session.execute(
            update(TaskModel)
            .where(TaskModel.id.in_(task_ids))
            .values(project_id=project_id, updated_at=utcnow())
        )
        self._session.flush()

    def detach_milestone(self, task_ids: list[int]) -> None:
        if not task_ids:
            return
        self._session.execute(
            update(TaskModel)
            .where(TaskModel.id.in_(task_ids))
            .values(milestone_id=None, updated_at=utcnow())
        )
        self._session.flush()

    def _to_entity(self, model: TaskModel) -> Task:
        return Task(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            category_id=model.category_id,
            priority=model.priority,
            urgency=model.urgency,
            status=TaskStatus(model.status),
            start_date=model.start_date,
            due_date=model.due_date,
            estimated_hours=model.estimated_hours,
            remaining_hours=model.remaining_hours,
            memo=model.memo,
            parent_task_id=model.parent_task_id,
            milestone_id=model.milestone_id,
            project_id=model.project_id,
            completed_at=model.completed_at,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, task: Task) -> TaskModel:
        return TaskModel(
            user_id=task.user_id,
            title=task.title,
            category_id=task.category_id,
            priority=task.priority,
            urgency=task.urgency,
            status=task.status.value if isinstance(task.status, TaskStatus) else task.status,
            start_date=task.start_date,
            due_date=task.due_date,
            estimated_hours=task.estimated_hours,
            remaining_hours=task.remaining_hours,
            memo=task.memo,
            parent_task_id=task.parent_task_id,
            milestone_id=task.milestone_id,
            project_id=task.project_id,
            completed_at=task.completed_at,
        )
