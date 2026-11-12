from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.domain.entities.milestone import Milestone
from src.domain.services.completion_forecast import CompletionForecast
from src.presentation.api.schemas.types import UtcDatetime


class MilestoneCreateRequest(BaseModel):
    name: str
    due_date: date | None = None
    description: str | None = None
    # Empty = uncategorized (can be attached to any task). A project's milestone attaches to tasks of that project and its descendants
    project_id: int | None = None


class MilestoneUpdateRequest(BaseModel):
    name: str | None = None
    due_date: date | None = None
    description: str | None = None
    # null makes it uncategorized. Tasks outside the new destination lose this milestone (ADR-0024)
    project_id: int | None = None


class MilestoneResponse(BaseModel):
    id: int
    user_id: int
    name: str
    due_date: date | None = None
    description: str | None = None
    project_id: int | None = None
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None
    # Expected finish (ADR-0058): the latest forecast end among the open tasks attached to it.
    # If forecast_unforecast_count tasks have no forecast, it means "at least"
    forecast_finish: date | None = None
    forecast_unforecast_count: int = 0
    forecast_overdue_days: int = 0

    model_config = {"from_attributes": True}

    @classmethod
    def with_forecast(cls, milestone: Milestone, forecast: CompletionForecast) -> MilestoneResponse:
        f = forecast.milestone(milestone)
        return cls.model_validate(milestone, from_attributes=True).model_copy(
            update={
                "forecast_finish": f.finish,
                "forecast_unforecast_count": f.unforecast_count,
                "forecast_overdue_days": f.overdue_days,
            }
        )
