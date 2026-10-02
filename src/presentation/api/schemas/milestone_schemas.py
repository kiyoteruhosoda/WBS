from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.presentation.api.schemas.types import UtcDatetime


class MilestoneCreateRequest(BaseModel):
    name: str
    due_date: date | None = None
    description: str | None = None
    # 空 = 未分類（どのタスクにも付けられる）。プロジェクトのものは、そのプロジェクトと子孫のタスクに付く
    project_id: int | None = None


class MilestoneUpdateRequest(BaseModel):
    name: str | None = None
    due_date: date | None = None
    description: str | None = None
    # null で未分類へ。移した先の外のタスクからは、このマイルストーンが外れる（ADR-0024）
    project_id: int | None = None


class MilestoneResponse(BaseModel):
    id: int
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None
    project_id: int | None = None
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
