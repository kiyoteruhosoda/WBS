from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.application.use_cases.settings_use_cases import UserSettingsUseCases
from src.presentation.api.dependencies import (
    AuthSettingsDep,
    CurrentUserDep,
    DbDep,
    SessionAuthDep,
)
from src.presentation.api.schemas.settings_schemas import (
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from src.presentation.api.session_cookies import set_access_cookie
from src.shared.clock import utcnow

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsResponse)
def get_settings(db: DbDep, current_user: CurrentUserDep) -> UserSettingsResponse:
    uc = UserSettingsUseCases(db)
    return UserSettingsResponse(**uc.get_settings(current_user.user_id))


@router.put("", response_model=UserSettingsResponse)
def update_settings(
    body: UserSettingsUpdateRequest,
    db: DbDep,
    current_user: CurrentUserDep,
    request: Request,
    response: Response,
    auth_settings: AuthSettingsDep,
    session_auth: SessionAuthDep,
) -> UserSettingsResponse:
    uc = UserSettingsUseCases(db)
    updated = UserSettingsResponse(**uc.update_settings(
        current_user.user_id,
        display_name=body.display_name,
        timezone=body.timezone,
        language=body.language,
    ))
    # Time zone and language are carried in the access token. Without reissuing it, the saving user's screen
    # keeps running with the old values until it expires (up to 5 minutes, ADR-0069). Other devices catch up on their next continuation (ADR-0071)
    if auth_settings.sso_enabled:
        token = session_auth.reissue_access(
            token=request.cookies.get(auth_settings.cookie_name), now=utcnow()
        )
        if token is not None:
            set_access_cookie(response, auth_settings, token)
    return updated
