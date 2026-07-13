from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class CategoryCreateRequest(BaseModel):
    name: str
    color: str | None = None
    sort_order: int = 0


class CategoryUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    id: int
    user_id: int
    name: str
    color: str | None = None
    sort_order: int
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
