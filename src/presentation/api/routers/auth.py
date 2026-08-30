"""SSO（OIDC）のログイン導線。

ブラウザの遷移で使う口（``/login`` と ``/callback``）は JSON ではなくリダイレクトを
返す。失敗もログイン画面へ戻し、画面側でメッセージを出す（コールバックに JSON の
エラーを出しても、利用者にはただの生テキストにしか見えない）。
"""

from __future__ import annotations

import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from src.domain.entities.login_transaction import DEFAULT_LOGIN_TRANSACTION_TTL
from src.domain.exceptions import AccessDeniedError, AuthenticationError, ValidationError
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

# 認可コードフロー 1 往復のあいだだけ生きる Cookie。中身は発行した state で、
# 「このコールバックはこのブラウザが始めた往復への返答か」を確かめるためだけに使う。
# セッション Cookie とは別名にしておく（名前の取り違えで寿命が混ざらないように）。
LOGIN_STATE_COOKIE = "sso_login_state"
LOGIN_STATE_COOKIE_MAX_AGE = int(DEFAULT_LOGIN_TRANSACTION_TTL.total_seconds())
# 別タブで同時にログインを始めることがあるので、直近の state を数個ぶん覚える。
# 1 つしか持たないと、後から始めた往復が先の往復を締め出してしまう。
LOGIN_STATE_COOKIE_CAPACITY = 3
# state は token_urlsafe（英数字と `-` `_`）なので、区切りに使っても値と衝突しない。
LOGIN_STATE_SEPARATOR = "."


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
    request: Request,
    settings: AuthSettingsDep,
    sso: SsoLoginDep,
    next_path: str | None = Query(default=None, alias="next"),
) -> RedirectResponse:
    """IdP の認可エンドポイントへ送り出す。

    ``next`` はログイン後に戻す画面。外部を指し得る値は ``RedirectTarget`` が
    既定のパスへ落とす（オープンリダイレクト対策）。

    併せて state を短命な Cookie にも置く。コールバックで両者が一致することを
    求めることで、この往復を始めたブラウザ以外がコールバックを使い切れなくなる。
    """
    started = sso.start_login(redirect_path=next_path, now=utcnow())
    # 302 でないと、IdP からの GET が POST として飛ぶ実装がある
    response = RedirectResponse(started.authorization_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=LOGIN_STATE_COOKIE,
        value=_remember_binding(
            request.cookies.get(LOGIN_STATE_COOKIE), started.browser_binding
        ),
        max_age=LOGIN_STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        # IdP からのトップレベル遷移で戻ってくるので lax でなければ届かない
        samesite=settings.cookie_samesite,
        path="/",
    )
    return response


@router.get("/callback", summary="SSO callback", response_class=RedirectResponse)
def complete_login(
    request: Request,
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
    if not _binding_matches(request.cookies.get(LOGIN_STATE_COOKIE), state):
        # このブラウザが始めた往復ではない。攻撃者が自分のログインのコールバックを
        # 踏ませて、他人のブラウザを自分のアカウントに繋ぐ手口を止める。
        return _back_to_login("invalid_request", "This login did not start in this browser")

    try:
        completed = sso.complete_login(code=code, state=state, now=utcnow())
    except AuthenticationError as exc:
        return _back_to_login("authentication_failed", str(exc))
    except AccessDeniedError as exc:
        return _back_to_login("access_denied", str(exc))
    except ValidationError as exc:
        # IdP の応答は正しくても、こちらの都合で受け入れられないことがある
        # （同じ発行者に別の sub で紐付け済み、など）。ここで JSON を返すと
        # 遷移の途中の利用者には生テキストにしか見えない。
        return _back_to_login("access_denied", str(exc))

    response = RedirectResponse(completed.redirect_path, status_code=status.HTTP_302_FOUND)
    # セッション Cookie を先に載せる（使い終えた一時 Cookie の掃除はその後）
    _set_session_cookie(response, settings, completed.session_token)
    _clear_login_state_cookie(response, settings)
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


def _remember_binding(cookie_value: str | None, state: str) -> str:
    """新しい state を先頭に足し、古いものから溢れさせる。"""
    previous = [v for v in (cookie_value or "").split(LOGIN_STATE_SEPARATOR) if v]
    remaining = [v for v in previous if v != state][: LOGIN_STATE_COOKIE_CAPACITY - 1]
    return LOGIN_STATE_SEPARATOR.join([state, *remaining])


def _binding_matches(cookie_value: str | None, state: str) -> bool:
    if not cookie_value:
        return False
    return any(
        hmac.compare_digest(candidate, state)
        for candidate in cookie_value.split(LOGIN_STATE_SEPARATOR)
        if candidate
    )


def _clear_login_state_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=LOGIN_STATE_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
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
