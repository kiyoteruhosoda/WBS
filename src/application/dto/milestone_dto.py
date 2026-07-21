from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.dto.unset import UNSET, UnsetType


@dataclass
class CreateMilestoneDTO:
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None

@dataclass
class UpdateMilestoneDTO:
    # UNSET = 変更しない / None = 明示的にクリアする
    name: str | UnsetType = UNSET
    due_date: date | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
