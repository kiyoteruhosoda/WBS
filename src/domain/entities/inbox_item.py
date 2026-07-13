from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class InboxItem:
    id: int | None
    user_id: int
    title: str
    memo: str | None = None
    converted_task_id: int | None = None
    converted_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
