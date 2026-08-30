"""SSO（OIDC）のログイン導線。

ブラウザの遷移で使う口（``/login`` と ``/callback``）は JSON ではなくリダイレクトを
返す。失敗もログイン画面へ戻し、画面側でメッセージを出す（コールバックに JSON の
エラーを出しても、利用者にはただの生テキストにしか見えない）。
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from src.domain.exceptions import AccessDeniedError, AuthenticationError
from src.infrastructure.auth.auth_settings import AuthSettings
from src.presentation.api.dependencies import (
    AuthSettingsDep,
    CurrentUserDep,
    SessionAuthDep,
    SsoLoginDep,
)
from src.presentation.api.schemas.auth_schemas import (
    AuthConfigResponse,
    CurrentUserResponse,
    LogoutResponse,
)
from src.shared.clock import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_ENDPOINT_PATH = "/api/auth/login"
LOGIN_PAGE_PATH = "/login"


@router.get("/config", response_model=AuthConfigResponse, summary="Authentication configuration")
def get_auth_config(settings: AuthSettingsDep) -> AuthConfigResponse:
    """ログイン画面を出すべきかどうかを画面側に伝える（認証不要）。"""
    if not settings.sso_enabled:
        return AuthConfigResponse(mode=settings.mode.value, sso_enabled=False)
    return AuthConfigResponse(
        mode=settings.mode.value,
        sso_enabled=True,
        provider_name=settings.provider_name,
        login_path=LOGIN_ENDPOINT_PATH,
    )


@router.get("/login", summary="Start SSO login", response_class=RedirectResponse)
def start_login(
    sso: SsoLoginDep,
    next_path: str | None = Query(default=None, alias="next"),
) -> RedirectResponse:
    """IdP の認可エンドポイントへ送り出す。

    ``next`` はログイン後に戻す画面。外部を指し得る値は ``RedirectTarget`` が
    既定のパスへ落とす（オープンリダイレクト対策）。
    """
    started = sso.start_login(redirect_path=next_path, now=utcnow())
    # 302 でないと、IdP からの GET が POST として飛ぶ実装がある
    return RedirectResponse(started.authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback", summary="SSO callback", response_class=RedirectResponse)
def complete_login(
    settings: AuthSettingsDep,
    sso: SsoLoginDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    if error:
        # 利用者が同意画面で断った場合などは IdP がここへエラーを返す
        return _back_to_login(error, error_description)
    if not code or not state:
        return _back_to_login("invalid_request", "code and state are required")

    try:
        completed = sso.complete_login(code=code, state=state, now=utcnow())
    except AuthenticationError as exc:
        return _back_to_login("authentication_failed", str(exc))
    except AccessDeniedError as exc:
        return _back_to_login("access_denied", str(exc))

    response = RedirectResponse(completed.redirect_path, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, settings, completed.session_token)
    return response


@router.get("/me", response_model=CurrentUserResponse, summary="Current user")
def get_current_user_profile(current_user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        display_name=current_user.display_name,
        timezone=current_user.timezone,
        language=current_user.language,
    )


@router.post("/logout", response_model=LogoutResponse, summary="Sign out")
def logout(
    request: Request,
    response: Response,
    settings: AuthSettingsDep,
    session_auth: SessionAuthDep,
    sso: SsoLoginDep,
) -> LogoutResponse:
    """こちら側のセッションを消し、IdP 側も切るための URL を返す。

    IdP へのリダイレクトは画面側に任せる（XHR でリダイレクトを返しても、
    ブラウザが勝手に追いかけてしまい、応答を読む前に画面が飛ぶ）。
    """
    token = request.cookies.get(settings.cookie_name)
    session_auth.revoke(token=token)
    _clear_session_cookie(response, settings)
    return LogoutResponse(
        end_session_url=sso.end_session_url(
            post_logout_redirect_uri=settings.post_logout_redirect_uri
        )
    )


def _back_to_login(error: str, description: str | None) -> RedirectResponse:
    params = {"error": error}
    if description:
        params["error_description"] = description
    return RedirectResponse(
        f"{LOGIN_PAGE_PATH}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )


def _set_session_cookie(response: Response, settings: AuthSettings, token: str) -> None:
    max_age = int(settings.session_ttl.total_seconds())
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=max_age,
        # JavaScript から読めないようにする（XSS でセッションを持ち出されない）
        httponly=True,
        # 既定は https 前提。localhost の開発時だけ AUTH_COOKIE_SECURE=false にする
        secure=settings.cookie_secure,
        # lax なら IdP からのトップレベル遷移では送られ、他サイトの埋め込みでは送られない
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
