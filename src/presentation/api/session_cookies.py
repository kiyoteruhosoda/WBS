"""ログインの Cookie の載せ方（ADR-0069・ADR-0071）。属性の付け方をここ 1 か所に集める。

⚠ **トークンを応答本文に載せない。** 本文にも返すと、XSS が新しいトークンを読めてしまい、
``httpOnly`` にした意味が無くなる。

- アクセストークン: 全部の口へ届く。⚠ **Cookie はトークン（5 分）より長く残す**（ADR-0071）。切れた後に
  画面を出さずに続ける往復が「誰の・どのログインか」を読むため（読むのは署名を確かめてから）
- リフレッシュトークン・ログアウトの札: **もう出さない**（ADR-0071）。以前のものが手元に残っていれば落とす
"""

from __future__ import annotations

from fastapi import Response

from src.application.dto.auth_dto import IssuedSessionDTO
from src.infrastructure.auth.auth_settings import (
    LOGOUT_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthSettings,
)

#: 以前の札の経路（ADR-0069）。落とすときに同じ経路を指さないと消えない
REFRESH_COOKIE_PATH = "/api/auth/refresh"
LOGOUT_COOKIE_PATH = "/api/auth/logout"


def set_access_cookie(response: Response, settings: AuthSettings, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=int(settings.sign_in_carry.total_seconds()),
        # JavaScript から読めないようにする（XSS でログインを持ち出されない）
        httponly=True,
        # 既定は https 前提。localhost の開発時だけ AUTH_COOKIE_SECURE=false にする
        secure=settings.cookie_secure,
        # lax なら IdP からのトップレベル遷移では送られ、他サイトの埋め込みでは送られない
        samesite=settings.cookie_samesite,
        path="/",
    )


def set_session_cookies(response: Response, settings: AuthSettings, issued: IssuedSessionDTO) -> None:
    """ログインが成立した（入った・続けた）。以前の札が残っていれば一緒に落とす。"""
    set_access_cookie(response, settings, issued.access_token)
    _clear(response, settings, ((REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH), (LOGOUT_COOKIE_NAME, LOGOUT_COOKIE_PATH)))


def clear_session_cookies(response: Response, settings: AuthSettings) -> None:
    _clear(
        response,
        settings,
        (
            (settings.cookie_name, "/"),
            (REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH),
            (LOGOUT_COOKIE_NAME, LOGOUT_COOKIE_PATH),
        ),
    )


def _clear(response: Response, settings: AuthSettings, cookies: tuple[tuple[str, str], ...]) -> None:
    for name, path in cookies:
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            path=path,
        )
