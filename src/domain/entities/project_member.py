"""Project member (task #544 / ADR-0055).

⚠ **Attached only to top-level projects.** Projects, tasks and milestones below are visible to all members of the root.
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
    #: Top-level project
    project_id: int
    user_id: int
    role: ProjectRole = ProjectRole.MEMBER
    #: Work hours per day. Forecasts treat "hours per day × allocation" as the time available to this project (ADR-0058)
    daily_hours: Decimal = DEFAULT_DAILY_HOURS
    #: Allocation (%). The share of the person's time given to this project
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
