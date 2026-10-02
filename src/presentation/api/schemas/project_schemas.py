from __future__ import annotations

from pydantic import BaseModel, Field

from src.application.use_cases.project_use_cases import ProjectView
from src.domain.value_objects.project_status import ProjectStatus
from src.presentation.api.schemas.types import UtcDatetime

# 色は #rrggbb（カテゴリと同じ形）
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_project_id: int | None = None
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    """送った欄だけ変える（null は空へ戻す）。親と並びは ``POST /projects/{id}/move``。"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectMoveRequest(BaseModel):
    """新しい親（null = 最上位）と、新しい兄弟の中の位置（0 = 先頭。省く・範囲外は末尾）。"""

    parent_project_id: int | None = None
    position: int | None = Field(default=None, ge=0)


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    name: str
    parent_project_id: int | None = None
    color: str | None = None
    description: str | None = None
    # active（進行中）/ archived（保管）
    status: str
    sort_order: int
    # 表示用の道筋（「親 / 子」）
    path: str
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    @classmethod
    def from_view(cls, view: ProjectView) -> ProjectResponse:
        p = view.project
        return cls(
            id=p.id or 0,
            user_id=p.user_id,
            name=p.name,
            parent_project_id=p.parent_project_id,
            color=p.color,
            description=p.description,
            status=p.status.value,
            sort_order=p.sort_order,
            path=view.path,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
