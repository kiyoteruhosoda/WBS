from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


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
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
