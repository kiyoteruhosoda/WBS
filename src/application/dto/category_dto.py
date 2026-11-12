from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.unset import UNSET, UnsetType


@dataclass
class CreateCategoryDTO:
    user_id: int
    name: str
    color: str | None = None
    sort_order: int = 0

@dataclass
class UpdateCategoryDTO:
    # UNSET = do not change / None = explicitly clear
    name: str | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    sort_order: int | UnsetType = UNSET
