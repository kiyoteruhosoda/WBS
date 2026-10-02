from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.unset import UNSET, UnsetType
from src.domain.value_objects.project_status import ProjectStatus


@dataclass
class CreateProjectDTO:
    user_id: int
    name: str
    parent_project_id: int | None = None
    color: str | None = None
    code: str | None = None
    description: str | None = None


@dataclass
class UpdateProjectDTO:
    # UNSET = 変更しない / None = 明示的にクリアする。親と並びは移動の口（MoveProjectDTO）で変える
    name: str | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    code: str | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
    status: ProjectStatus | UnsetType = UNSET


@dataclass
class MoveProjectDTO:
    #: 新しい親（None = 最上位）
    parent_project_id: int | None
    #: 新しい兄弟の中の位置（0 = 先頭。None・範囲外は末尾）
    position: int | None = None
