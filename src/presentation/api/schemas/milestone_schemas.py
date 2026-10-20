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
    # 空 = 未分類（どのタスクにも付けられる）。プロジェクトのものは、そのプロジェクトと子孫のタスクに付く
    project_id: int | None = None


class MilestoneUpdateRequest(BaseModel):
    name: str | None = None
    due_date: date | None = None
    description: str | None = None
    # null で未分類へ。移した先の外のタスクからは、このマイルストーンが外れる（ADR-0024）
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
    # 終わる見込み（ADR-0058）: 付いた開いているタスクの見込みの終わりのうち、いちばん遅い日。
    # 見込みの出ないタスクが forecast_unforecast_count 件あれば「少なくとも」の意味
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
