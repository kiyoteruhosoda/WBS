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
    # UNSET = do not change / None = explicitly clear. Parent and position are changed via the move endpoint (MoveProjectDTO)
    name: str | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    code: str | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
    status: ProjectStatus | UnsetType = UNSET


@dataclass
class MoveProjectDTO:
    #: New parent (None = top level)
    parent_project_id: int | None
    #: New position among siblings (0 = first; None or out of range = last)
    position: int | None = None
