"""プロジェクトのメンバー（task #544 / ADR-0055）。

⚠ **いちばん上のプロジェクトにだけ付く。** その下のプロジェクト・タスク・マイルストーンは根のメンバー全員に見える。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.project_role import ProjectRole


@dataclass
class ProjectMember:
    id: int | None
    #: いちばん上のプロジェクト
    project_id: int
    user_id: int
    role: ProjectRole = ProjectRole.MEMBER
    created_at: datetime | None = None

    @property
    def is_manager(self) -> bool:
        return self.role is ProjectRole.MANAGER
