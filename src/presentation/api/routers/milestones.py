from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from src.application.dto.milestone_dto import CreateMilestoneDTO, UpdateMilestoneDTO
from src.application.use_cases.completion_forecast_use_cases import CompletionForecastUseCases
from src.application.use_cases.milestone_use_cases import MilestoneUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.milestone_schemas import (
    MilestoneCreateRequest,
    MilestoneResponse,
    MilestoneUpdateRequest,
)

router = APIRouter(prefix="/milestones", tags=["milestones"])


@router.get("", response_model=list[MilestoneResponse])
def list_milestones(
    db: DbDep,
    current_user: CurrentUserDep,
    project_id: Annotated[
        int | None, Query(description="Only those in this project and its descendant projects")
    ] = None,
    unclassified: Annotated[
        bool, Query(description="If true, only those without a project (uncategorized)")
    ] = False,
) -> list[MilestoneResponse]:
    uc = MilestoneUseCases(db)
    milestones = uc.list_milestones(
        current_user.user_id, project_id=project_id, unclassified=unclassified
    )
    # The forecast date is computed on every read (ADR-0058)
    forecast = CompletionForecastUseCases(db).forecast(current_user.user_id)
    return [MilestoneResponse.with_forecast(m, forecast) for m in milestones]


@router.post("", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_milestone(body: MilestoneCreateRequest, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    dto = CreateMilestoneDTO(
        user_id=current_user.user_id, name=body.name, due_date=body.due_date,
        description=body.description, project_id=body.project_id,
    )
    return MilestoneResponse.model_validate(uc.create_milestone(dto), from_attributes=True)


@router.get("/{milestone_id}", response_model=MilestoneResponse)
def get_milestone(milestone_id: int, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    forecast = CompletionForecastUseCases(db).forecast(current_user.user_id)
    return MilestoneResponse.with_forecast(uc.get_milestone(milestone_id, current_user.user_id), forecast)


@router.put("/{milestone_id}", response_model=MilestoneResponse)
def update_milestone(milestone_id: int, body: MilestoneUpdateRequest, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    # Pass only the submitted fields to the DTO (omitted ones stay UNSET = unchanged).
    # An explicit null clears the value.
    dto = UpdateMilestoneDTO(**body.model_dump(exclude_unset=True))
    return MilestoneResponse.model_validate(uc.update_milestone(milestone_id, current_user.user_id, dto), from_attributes=True)


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(milestone_id: int, db: DbDep, current_user: CurrentUserDep) -> None:
    uc = MilestoneUseCases(db)
    uc.delete_milestone(milestone_id, current_user.user_id)
