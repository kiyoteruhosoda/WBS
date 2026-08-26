from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.application.user_clock import UserClock
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.database.models import CategoryModel, TaskModel, WorkLogModel


class ReviewUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._clock = UserClock(session)

    def get_weekly_review(self, user_id: int, week: str) -> dict:
        monday = datetime.strptime(week + "-1", "%G-W%V-%u").date()
        sunday = monday + timedelta(days=6)

        completed_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.status == TaskStatus.DONE.value,
                TaskModel.completed_at >= monday,
                TaskModel.completed_at <= sunday,
                TaskModel.deleted_at.is_(None),
            )
        ).scalar() or 0

        new_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.created_at >= monday,
                TaskModel.created_at <= sunday,
                TaskModel.deleted_at.is_(None),
            )
        ).scalar() or 0

        overdue_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.deleted_at.is_(None),
                TaskModel.status.notin_([TaskStatus.DONE.value, TaskStatus.CANCELLED.value]),
                TaskModel.due_date < self._clock.today(user_id),
            )
        ).scalar() or 0

        total_hours = self._session.execute(
            select(func.sum(WorkLogModel.hours)).where(
                WorkLogModel.user_id == user_id,
                WorkLogModel.deleted_at.is_(None),
                WorkLogModel.work_date >= monday,
                WorkLogModel.work_date <= sunday,
            )
        ).scalar() or 0

        rows = self._session.execute(
            select(TaskModel.category_id, func.sum(WorkLogModel.hours)).
            join(WorkLogModel, WorkLogModel.task_id == TaskModel.id).
            where(
                WorkLogModel.user_id == user_id,
                WorkLogModel.deleted_at.is_(None),
                WorkLogModel.work_date >= monday,
                WorkLogModel.work_date <= sunday,
            ).group_by(TaskModel.category_id)
        ).all()

        hours_by_category: dict[str, float] = {}
        for category_id, hours in rows:
            if category_id is None:
                key = "uncategorized"
            else:
                cat = self._session.get(CategoryModel, category_id)
                key = cat.name if cat else str(category_id)
            hours_by_category[key] = float(hours or 0)

        return {
            "week": week,
            "monday": str(monday),
            "sunday": str(sunday),
            "completed_count": completed_count,
            "new_count": new_count,
            "overdue_count": overdue_count,
            "total_hours": float(total_hours),
            "hours_by_category": hours_by_category,
        }
