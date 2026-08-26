"""ダッシュボードの応答。

素の ``dict`` で返すと、中のタスクに載った ``datetime`` は FastAPI の
``jsonable_encoder`` が ``Z`` 無しの ISO 文字列にする。同じタスクでも
``/api/tasks`` は ``Z`` 付き、``/api/dashboard/today`` は ``Z`` 無しになり、
JST の閲覧者にはダッシュボードだけ 9 時間ずれて見える（HANDOVER §14）。
``TaskResponse`` を通してその口を塞ぐ。
"""

from __future__ import annotations

from pydantic import BaseModel

from src.presentation.api.schemas.task_schemas import TaskResponse


class TodayBucketsResponse(BaseModel):
    buckets: dict[str, list[TaskResponse]]


class KpiResponse(BaseModel):
    total_tasks: int
    incomplete_tasks: int
    overdue_tasks: int
    this_week_completed: int
    this_week_hours: float


__all__ = ["KpiResponse", "TodayBucketsResponse"]
