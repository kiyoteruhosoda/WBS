"""このアプリが自分で出すトークンを JWT（HS256）で作る・読む（ADR-0069）。

⚠ **``type`` で 3 種類を分ける。** ログアウトの札で更新できたり、リフレッシュトークンで API を
叩けたりしないように、読むときに必ず見る。

期限は ``now`` と比べる（ライブラリに時計を持たせない。時刻の口は ``src/shared/clock.py`` 1 つ）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.session_tokens import (
    AccessTokenContents,
    RefreshTokenContents,
    SessionTokens,
)

_ALGORITHM = "HS256"
#: 発行者と宛先。別のアプリや環境のトークンは鍵で落ちるが、鍵を取り違えても混ざらないように名乗る
_NAME = "wbs"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
TYPE_LOGOUT = "logout"
CLAIM_SESSION = "rsid"


def _timestamp(moment: datetime) -> int:
    """naive な UTC をエポック秒へ（``src/shared/clock.py`` の契約）。"""
    return int(moment.replace(tzinfo=UTC).timestamp())


class JwtSessionTokens(SessionTokens):
    def __init__(self, *, signing_key: str, access_lifetime: timedelta, refresh_lifetime: timedelta) -> None:
        self._key = signing_key
        self._access_lifetime = access_lifetime
        self._refresh_lifetime = refresh_lifetime

    @property
    def refresh_lifetime(self) -> timedelta:
        return self._refresh_lifetime

    def access_token(self, user: AuthenticatedUserDTO, *, session_id: str, now: datetime) -> str:
        return self._encode(
            {
                "sub": str(user.user_id),
                "type": TYPE_ACCESS,
                CLAIM_SESSION: session_id,
                "email": user.email,
                "name": user.display_name,
                "tz": user.timezone,
                "lang": user.language,
                "can_create_projects": user.can_create_projects,
            },
            now,
            self._access_lifetime,
        )

    def refresh_token(self, user_id: int, *, session_id: str, jti: str, now: datetime) -> str:
        return self._encode(
            {"sub": str(user_id), "type": TYPE_REFRESH, CLAIM_SESSION: session_id, "jti": jti},
            now,
            self._refresh_lifetime,
        )

    def logout_token(self, user_id: int, *, session_id: str, now: datetime) -> str:
        return self._encode(
            {"sub": str(user_id), "type": TYPE_LOGOUT, CLAIM_SESSION: session_id},
            now,
            self._refresh_lifetime,
        )

    def read_access(self, token: str, *, now: datetime) -> AccessTokenContents | None:
        claims = self._decode(token, TYPE_ACCESS, now)
        if claims is None:
            return None
        return AccessTokenContents(
            user=AuthenticatedUserDTO(
                user_id=int(claims["sub"]),
                email=str(claims.get("email") or ""),
                display_name=str(claims.get("name") or ""),
                timezone=str(claims.get("tz") or ""),
                language=str(claims.get("lang") or ""),
                can_create_projects=claims.get("can_create_projects") is True,
            ),
            session_id=str(claims[CLAIM_SESSION]),
        )

    def read_refresh(self, token: str, *, now: datetime) -> RefreshTokenContents | None:
        claims = self._decode(token, TYPE_REFRESH, now)
        if claims is None or not isinstance(claims.get("jti"), str):
            return None
        return RefreshTokenContents(
            user_id=int(claims["sub"]), session_id=str(claims[CLAIM_SESSION]), jti=claims["jti"]
        )

    def read_logout(self, token: str, *, now: datetime) -> str | None:
        claims = self._decode(token, TYPE_LOGOUT, now)
        return None if claims is None else str(claims[CLAIM_SESSION])

    def _encode(self, claims: dict[str, Any], now: datetime, lifetime: timedelta) -> str:
        return jwt.encode(
            {
                **claims,
                "iss": _NAME,
                "aud": _NAME,
                "iat": _timestamp(now),
                "exp": _timestamp(now + lifetime),
            },
            self._key,
            algorithm=_ALGORITHM,
        )

    def _decode(self, token: str, expected_type: str, now: datetime) -> dict[str, Any] | None:
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=[_ALGORITHM],
                audience=_NAME,
                issuer=_NAME,
                options={
                    "require": ["exp", "sub", CLAIM_SESSION, "type"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
        except jwt.InvalidTokenError:
            return None
        if claims.get("type") != expected_type or not str(claims["sub"]).isdigit():
            return None
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= _timestamp(now):
            return None
        return claims
