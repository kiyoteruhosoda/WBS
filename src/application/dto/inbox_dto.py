from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass
class CreateInboxItemDTO:
    user_id: int
    title: str
    memo: str | None = None

@dataclass
class ConvertInboxItemDTO:
    title: str | None = None
    category_id: int | None = None
    priority: int = 3
    urgency: int = 3
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    memo: str | None = None
