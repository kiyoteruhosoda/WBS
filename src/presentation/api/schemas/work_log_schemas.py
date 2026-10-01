from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from src.domain.value_objects.work_log_source import WorkLogSource
from src.presentation.api.schemas.types import UtcDatetime


class WorkLogCreateRequest(BaseModel):
    task_id: int
    work_date: date
    hours: Decimal
    memo: str | None = None


class WorkLogUpdateRequest(BaseModel):
    work_date: date | None = None
    hours: Decimal | None = None
    memo: str | None = None


class WorkLogResponse(BaseModel):
    id: int
    user_id: int
    task_id: int
    work_date: date
    hours: float
    memo: str | None = None
    source: WorkLogSource = WorkLogSource.MANUAL
    closing_period_id: int | None = None
    duration_seconds: int | None = None
    """締めで作った行（``source=closing``）の正確な長さ（秒）。``hours`` は小数 2 桁に収めた値。"""
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
