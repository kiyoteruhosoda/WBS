"""プロジェクトのメンバー（task #544 / ADR-0055）。

⚠ **いちばん上のプロジェクトにだけ付く。** その下のプロジェクト・タスク・マイルストーンは根のメンバー全員に見える。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.exceptions import ValidationError

from src.domain.value_objects.project_role import ProjectRole

DEFAULT_DAILY_HOURS = Decimal(8)
DEFAULT_ENGAGEMENT_PERCENT = 100
MAX_DAILY_HOURS = Decimal(24)


@dataclass
class ProjectMember:
    id: int | None
    #: いちばん上のプロジェクト
    project_id: int
    user_id: int
    role: ProjectRole = ProjectRole.MEMBER
    #: 1 日の工数（時間）。見込みの計算で「1 日の工数 × 従事率」をこのプロジェクトに使える時間とする（ADR-0058）
    daily_hours: Decimal = DEFAULT_DAILY_HOURS
    #: 従事率（%）。その人がこのプロジェクトに割く割合
    engagement_percent: int = DEFAULT_ENGAGEMENT_PERCENT
    created_at: datetime | None = None

    def set_capacity(self, daily_hours: Decimal, engagement_percent: int) -> None:
        if not Decimal(0) <= daily_hours <= MAX_DAILY_HOURS:
            raise ValidationError("daily hours must be between 0 and 24")
        if not 0 <= engagement_percent <= 100:
            raise ValidationError("engagement must be between 0 and 100 percent")
        self.daily_hours = daily_hours
        self.engagement_percent = engagement_percent

    @property
    def is_manager(self) -> bool:
        return self.role is ProjectRole.MANAGER
