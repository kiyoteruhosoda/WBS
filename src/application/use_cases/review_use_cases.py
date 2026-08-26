from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.application.user_clock import UserClock
from src.domain.exceptions import ValidationError
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.database.models import CategoryModel, TaskModel, WorkLogModel


def _monday_of(week: str) -> date:
    """``2026-W36`` の月曜。読めない値は 500 ではなく 422 で返す。"""
    try:
        return datetime.strptime(week + "-1", "%G-W%V-%u").date()
    except ValueError as exc:
        raise ValidationError(f"week は YYYY-Www 形式で指定する: {week!r}") from exc


class ReviewUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._clock = UserClock(session)

    def get_weekly_review(self, user_id: int, week: str | None = None) -> dict:
        # 「今週」も「今日」も利用者のタイムゾーンで決まる。サーバ（UTC）基準で取ると、
        # JST の利用者にとって月曜 0:00〜9:00 のあいだ前の週・前の日にずれる。
        today = self._clock.today(user_id)
        monday = _monday_of(week) if week else today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        # 応答の week は必ず埋める（省略時はいま解決した週を返す）
        week = week or monday.strftime("%G-W%V")
        # 日付は利用者のタイムゾーンで切ったもの。保存値は UTC なので、そのまま
        # DATETIME 列と比べず UTC の半開区間へ直してから突き合わせる。
        week_from, week_until = self._clock.utc_window(user_id, monday, sunday)

        completed_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.status == TaskStatus.DONE.value,
                TaskModel.completed_at >= week_from,
                TaskModel.completed_at < week_until,
                TaskModel.deleted_at.is_(None),
            )
        ).scalar() or 0

        new_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.created_at >= week_from,
                TaskModel.created_at < week_until,
                TaskModel.deleted_at.is_(None),
            )
        ).scalar() or 0

        overdue_count = self._session.execute(
            select(func.count()).where(
                TaskModel.user_id == user_id,
                TaskModel.deleted_at.is_(None),
                TaskModel.status.notin_([TaskStatus.DONE.value, TaskStatus.CANCELLED.value]),
                TaskModel.due_date < today,
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
