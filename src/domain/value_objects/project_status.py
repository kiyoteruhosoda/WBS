"""プロジェクトの状態（task #187 / ADR-0024）。"""

from __future__ import annotations

import enum


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    """進行中。タスクやマイルストーンの選び先に出る。"""
    ARCHIVED = "archived"
    """保管。木には薄く残る（中のタスクと実績はそのまま読める）が、選び先には出ない。"""
