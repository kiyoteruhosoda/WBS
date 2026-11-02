"""ログインの Cookie の載せ方（ADR-0069）。属性の付け方をここ 1 か所に集める。

⚠ **トークンを応答本文に載せない。** 本文にも返すと、XSS が更新の口を叩いて新しいトークンを読めてしまい、
``httpOnly`` にした意味が無くなる。

- アクセストークン: 全部の口へ届く。寿命はトークンと同じ
- リフレッシュトークン: **更新の口へだけ**届く（長命な資格情報が送られる回数を増やさない）
- ログアウトの札: **ログアウトの口へだけ**届く。更新の Cookie の経路を広げるより、
  「終わらせることしかできない札」を別に置くほうが漏れたときの被害が小さい
"""

from __future__ import annotations

from fastapi import Response

from src.application.dto.auth_dto import IssuedSessionDTO
from src.infrastructure.auth.auth_settings import (
    LOGOUT_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthSettings,
)

REFRESH_COOKIE_PATH = "/api/auth/refresh"
LOGOUT_COOKIE_PATH = "/api/auth/logout"


def set_access_cookie(response: Response, settings: AuthSettings, token: str) -> None:
    _set(response, settings, settings.cookie_name, token, settings.access_token_ttl.total_seconds(), "/")


def set_session_cookies(response: Response, settings: AuthSettings, issued: IssuedSessionDTO) -> None:
    """⚠ ``refresh_token`` が空のときは更新の Cookie に触らない（同時に走った更新の勝った側のものを残す）。"""
    set_access_cookie(response, settings, issued.access_token)
    refresh_seconds = settings.refresh_token_ttl.total_seconds()
    if issued.refresh_token is not None:
        _set(response, settings, REFRESH_COOKIE_NAME, issued.refresh_token, refresh_seconds, REFRESH_COOKIE_PATH)
    if issued.logout_token is not None:
        _set(response, settings, LOGOUT_COOKIE_NAME, issued.logout_token, refresh_seconds, LOGOUT_COOKIE_PATH)


def clear_session_cookies(response: Response, settings: AuthSettings) -> None:
    for name, path in (
        (settings.cookie_name, "/"),
        (REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH),
        (LOGOUT_COOKIE_NAME, LOGOUT_COOKIE_PATH),
    ):
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            path=path,
        )


def _set(
    response: Response, settings: AuthSettings, name: str, value: str, max_age: float, path: str
) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=int(max_age),
        # JavaScript から読めないようにする（XSS でログインを持ち出されない）
        httponly=True,
        # 既定は https 前提。localhost の開発時だけ AUTH_COOKIE_SECURE=false にする
        secure=settings.cookie_secure,
        # lax なら IdP からのトップレベル遷移では送られ、他サイトの埋め込みでは送られない
        samesite=settings.cookie_samesite,
        path=path,
    )
