"""How the login cookies are set (ADR-0069, ADR-0071). Attributes are set in this one place.

⚠ **Never put tokens in the response body.** Returning them in the body too lets XSS read the new token
and defeats the point of ``httpOnly``.

- Access token: sent to every endpoint. ⚠ **The cookie outlives the token (5 minutes)** (ADR-0071), so that after
    expiry the silent continuation round trip can tell "whose login, which login" (read only after verifying the signature)
- Refresh token and logout ticket: **no longer issued** (ADR-0071). Old ones still held by the client are cleared
"""

from __future__ import annotations

from fastapi import Response

from src.application.dto.auth_dto import IssuedSessionDTO
from src.infrastructure.auth.auth_settings import (
    LOGOUT_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthSettings,
)

#: Path of the old tickets (ADR-0069). Clearing must use the same path or they are not removed
REFRESH_COOKIE_PATH = "/api/auth/refresh"
LOGOUT_COOKIE_PATH = "/api/auth/logout"


def set_access_cookie(response: Response, settings: AuthSettings, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=int(settings.sign_in_carry.total_seconds()),
        # Not readable from JavaScript (so XSS cannot carry off the login)
        httponly=True,
        # Assumes https by default. Set AUTH_COOKIE_SECURE=false only for localhost development
        secure=settings.cookie_secure,
        # With lax, it is sent on top-level navigations from the IdP but not in other sites' embeds
        samesite=settings.cookie_samesite,
        path="/",
    )


def set_session_cookies(response: Response, settings: AuthSettings, issued: IssuedSessionDTO) -> None:
    """A login was established (signed in or continued). Old tickets, if still present, are cleared too."""
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
