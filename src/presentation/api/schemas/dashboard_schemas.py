"""ダッシュボードの応答（KPI だけ。今日のタスクは ``/api/today``、ADR-0015）。"""

from __future__ import annotations

from pydantic import BaseModel


class KpiResponse(BaseModel):
    total_tasks: int
    incomplete_tasks: int
    overdue_tasks: int
    this_week_completed: int
    this_week_hours: float


__all__ = ["KpiResponse"]
