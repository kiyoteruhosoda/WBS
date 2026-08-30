from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.milestone_dto import CreateMilestoneDTO, UpdateMilestoneDTO
from src.application.use_cases.milestone_use_cases import MilestoneUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.milestone_schemas import (
    MilestoneCreateRequest,
    MilestoneResponse,
    MilestoneUpdateRequest,
)

router = APIRouter(prefix="/milestones", tags=["milestones"])


@router.get("", response_model=list[MilestoneResponse])
def list_milestones(db: DbDep, current_user: CurrentUserDep) -> list[MilestoneResponse]:
    uc = MilestoneUseCases(db)
    return [MilestoneResponse.model_validate(m, from_attributes=True) for m in uc.list_milestones(current_user.user_id)]


@router.post("", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_milestone(body: MilestoneCreateRequest, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    dto = CreateMilestoneDTO(user_id=current_user.user_id, name=body.name, due_date=body.due_date, description=body.description)
    return MilestoneResponse.model_validate(uc.create_milestone(dto), from_attributes=True)


@router.get("/{milestone_id}", response_model=MilestoneResponse)
def get_milestone(milestone_id: int, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    return MilestoneResponse.model_validate(uc.get_milestone(milestone_id, current_user.user_id), from_attributes=True)


@router.put("/{milestone_id}", response_model=MilestoneResponse)
def update_milestone(milestone_id: int, body: MilestoneUpdateRequest, db: DbDep, current_user: CurrentUserDep) -> MilestoneResponse:
    uc = MilestoneUseCases(db)
    # 送信されたフィールドのみ DTO へ渡す（未指定は UNSET のまま＝変更しない）。
    # 明示的な null はクリアとして反映される。
    dto = UpdateMilestoneDTO(**body.model_dump(exclude_unset=True))
    return MilestoneResponse.model_validate(uc.update_milestone(milestone_id, current_user.user_id, dto), from_attributes=True)


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(milestone_id: int, db: DbDep, current_user: CurrentUserDep) -> None:
    uc = MilestoneUseCases(db)
    uc.delete_milestone(milestone_id, current_user.user_id)
