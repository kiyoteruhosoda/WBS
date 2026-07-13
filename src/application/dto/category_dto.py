from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CreateCategoryDTO:
    user_id: int
    name: str
    color: str | None = None
    sort_order: int = 0

@dataclass
class UpdateCategoryDTO:
    name: str | None = None
    color: str | None = None
    sort_order: int | None = None
