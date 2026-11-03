from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskRemovalAction(StrEnum):
    DELETE = "delete"
    """確定した実績が無い: 消す。"""
    ARCHIVE = "archive"
    """確定した実績がある: 消さずにアーカイブする。"""


@dataclass(frozen=True)
class TaskRemovalPreview:
    """タスクを消すとどうなるか（確認の窓に出す。ADR-0046）。"""

    task_id: int
    title: str
    action: TaskRemovalAction
    # 確定した実績（work_logs）の合計
    work_log_hours: float
    archived: bool
