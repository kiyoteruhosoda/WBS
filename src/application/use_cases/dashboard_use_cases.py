from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.application.user_clock import UserClock
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.database.models import TaskModel, WorkLogModel


class DashboardUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._clock = UserClock(session)

    def _user_today(self, user_id: int) -> date:
        return self._clock.today(user_id)

    def get_kpi(self, user_id: int) -> dict:
        today = self._user_today(user_id)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        # 週の区切りは利用者の日付。保存値は UTC なので UTC の半開区間へ直す。
        week_from, week_until = self._clock.utc_window(user_id, week_start, week_end)
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
                TaskModel.completed_at >= week_from,
                TaskModel.completed_at < week_until,
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
