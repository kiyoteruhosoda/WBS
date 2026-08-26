from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from src.presentation.api.schemas.types import UtcDatetime


class InboxItemCreateRequest(BaseModel):
    title: str
    memo: str | None = None


class InboxItemConvertRequest(BaseModel):
    title: str | None = None
    category_id: int | None = None
    priority: int = 3
    urgency: int = 3
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    memo: str | None = None


class InboxItemResponse(BaseModel):
    id: int
    user_id: int
    title: str
    memo: str | None = None
    converted_task_id: int | None = None
    converted_at: UtcDatetime | None = None
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
