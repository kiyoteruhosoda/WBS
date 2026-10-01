"""プロジェクト（task #187 / ADR-0024）。

⚠ **多段に入れ子にできる**（深さに決まりは無い）。親は ``parent_project_id``（隣接リスト）で持ち、
子孫は再帰 CTE で引く（nolumiatask の ADR-0046 と同じ形）。環は作らせない（``ProjectTree``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.project_status import ProjectStatus

NAME_MAX_LENGTH = 200


def project_name(raw: str) -> str:
    """前後の空白を落とした名前。空・長すぎるものは断る。"""
    name = raw.strip()
    if not name:
        raise ValidationError("a project needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a project name must be at most {NAME_MAX_LENGTH} characters")
    return name


@dataclass
class Project:
    id: int | None
    user_id: int
    name: str
    #: None = 最上位
    parent_project_id: int | None = None
    color: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    #: 兄弟の中の並び（0 から。動かすと兄弟ごと振り直す）
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_archived(self) -> bool:
        return self.status is ProjectStatus.ARCHIVED
