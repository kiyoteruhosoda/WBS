from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.database.models import TaskModel, WorkLogModel
from src.application.use_cases.task_use_cases import TaskUseCases
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository


class DashboardUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._task_repo = SqlAlchemyTaskRepository(session)
        self._task_uc = TaskUseCases(session)

    def get_today_buckets(self, user_id: int) -> dict:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        active_statuses = [TaskStatus.TODO.value, TaskStatus.DOING.value, TaskStatus.WAITING.value]
        stmt = select(TaskModel).where(
            TaskModel.user_id == user_id,
            TaskModel.deleted_at.is_(None),
            TaskModel.status.in_(active_statuses),
        )
        tasks = list(self._session.scalars(stmt))
        buckets: dict[str, list] = {"OVERDUE": [], "TODAY": [], "TOMORROW": [], "DOING": [], "STARTED": []}
        seen_ids: set[int] = set()
        for t in tasks:
            enriched = self._task_uc._enrich(self._task_repo._to_entity(t))
            tid = t.id
            bucket = None
            if t.due_date and t.due_date < today:
                bucket = "OVERDUE"
            elif t.due_date == today:
                bucket = "TODAY"
            elif t.due_date == tomorrow:
                bucket = "TOMORROW"
            elif t.status == TaskStatus.DOING.value:
                bucket = "DOING"
            elif t.start_date and t.start_date <= today and t.status == TaskStatus.TODO.value:
                bucket = "STARTED"
            if bucket and tid not in seen_ids:
                buckets[bucket].append(enriched)
                seen_ids.add(tid)
        return {"buckets": buckets}

    def get_kpi(self, user_id: int) -> dict:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        total = self._session.execute(
            select(func.count()).where(TaskModel.user_id == user_id, TaskModel.deleted_at.is_(None))
        ).scalar() or 0
        incomplete = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.deleted_at.is_(None),
                TaskModel.status.notin_([TaskStatus.DONE.value, TaskStatus.CANCELLED.value]),
            )
        ).scalar() or 0
        overdue = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.deleted_at.is_(None),
                TaskModel.status.notin_([TaskStatus.DONE.value, TaskStatus.CANCELLED.value]),
                TaskModel.due_date < today,
            )
        ).scalar() or 0
        this_week_completed = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.status == TaskStatus.DONE.value,
                TaskModel.completed_at >= week_start,
                TaskModel.completed_at <= week_end,
            )
        ).scalar() or 0
        this_week_hours = self._session.execute(
            select(func.sum(WorkLogModel.hours)).where(
                WorkLogModel.user_id == user_id,
                WorkLogModel.deleted_at.is_(None),
                WorkLogModel.work_date >= week_start,
                WorkLogModel.work_date <= week_end,
            )
        ).scalar() or 0
        return {
            "total_tasks": total,
            "incomplete_tasks": incomplete,
            "overdue_tasks": overdue,
            "this_week_completed": this_week_completed,
            "this_week_hours": float(this_week_hours),
        }
