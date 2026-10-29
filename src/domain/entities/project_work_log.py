from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ProjectWorkLog:
    """プロジェクトだけの実績: WBS のタスクに結ばない、プロジェクトの時間（task #708 / ADR-0064）。

    いまは Tracker で締めた時間だけが入る（``tracker_first_day`` はその締めの期間の初日）。
    """

    id: int | None
    user_id: int
    project_id: int
    work_date: date
    seconds: int
    tracker_first_day: date
    deleted_at: datetime | None = None
    created_at: datetime | None = None


__all__ = ["ProjectWorkLog"]
