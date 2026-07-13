from __future__ import annotations
from dataclasses import dataclass
from datetime import date

@dataclass
class CreateMilestoneDTO:
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None

@dataclass
class UpdateMilestoneDTO:
    name: str | None = None
    due_date: date | None = None
    description: str | None = None
