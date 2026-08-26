from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.presentation.api.schemas.types import UtcDatetime


class MilestoneCreateRequest(BaseModel):
    name: str
    due_date: date | None = None
    description: str | None = None


class MilestoneUpdateRequest(BaseModel):
    name: str | None = None
    due_date: date | None = None
    description: str | None = None


class MilestoneResponse(BaseModel):
    id: int
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
