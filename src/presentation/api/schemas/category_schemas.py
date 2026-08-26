from __future__ import annotations

from pydantic import BaseModel

from src.presentation.api.schemas.types import UtcDatetime


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
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
