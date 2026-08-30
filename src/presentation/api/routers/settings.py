from __future__ import annotations

from fastapi import APIRouter

from src.application.use_cases.settings_use_cases import UserSettingsUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.settings_schemas import (
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsResponse)
def get_settings(db: DbDep, current_user: CurrentUserDep) -> UserSettingsResponse:
    uc = UserSettingsUseCases(db)
    return UserSettingsResponse(**uc.get_settings(current_user.user_id))


@router.put("", response_model=UserSettingsResponse)
def update_settings(body: UserSettingsUpdateRequest, db: DbDep, current_user: CurrentUserDep) -> UserSettingsResponse:
    uc = UserSettingsUseCases(db)
    return UserSettingsResponse(**uc.update_settings(
        current_user.user_id,
        display_name=body.display_name,
        timezone=body.timezone,
        language=body.language,
    ))
