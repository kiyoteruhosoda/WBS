from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskRemovalAction(StrEnum):
    DELETE = "delete"
    """打刻も実績も無い: 消す。"""
    ARCHIVE = "archive"
    """打刻か実績がある: 消さずにしまう。"""


@dataclass(frozen=True)
class TaskRemovalPreview:
    """タスクを消すとどうなるか（確認の窓に出す。ADR-0046）。"""

    task_id: int
    title: str
    action: TaskRemovalAction
    # 付いている打刻の数と長さの合計（走っている打刻は今まで）
    time_entries: int
    tracked_seconds: int
    # 確定した実績（work_logs）の合計
    work_log_hours: float
    # このタスクを指す WinTrack の規則（しまうと止まる）
    tracking_rules: int
    # 消すこともしまうこともできない理由（running = 計測中）。できれば None
    blocked_by: str | None
    archived: bool
