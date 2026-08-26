from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

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
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
