from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Category:
    id: int | None
    user_id: int
    name: str
    color: str | None = None
    sort_order: int = 0
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
