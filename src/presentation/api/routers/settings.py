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
    # タイムゾーンと言語はアクセストークンに載っている。出し直さないと、保存した本人の画面が
    # 寿命（最長 5 分）まで古い値で動く（ADR-0069）。ほかの端末は次に続けたとき（ADR-0071）に揃う
    if auth_settings.sso_enabled:
        token = session_auth.reissue_access(
            token=request.cookies.get(auth_settings.cookie_name), now=utcnow()
        )
        if token is not None:
            set_access_cookie(response, auth_settings, token)
    return updated
