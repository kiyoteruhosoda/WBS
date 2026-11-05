"""このアプリが自分で出すトークンを JWT（HS256）で作る・読む（ADR-0069・ADR-0071）。

出すのはアクセストークンだけ。⚠ **読むときは ``type`` を必ず見る。** 以前出していたリフレッシュトークン・
ログアウトの札（``refresh`` / ``logout``）が手元に残っていても、API を叩けないように。

期限は ``now`` と比べる（ライブラリに時計を持たせない。時刻の口は ``src/shared/clock.py`` 1 つ）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.session_tokens import AccessTokenContents, SessionTokens
from src.domain.value_objects.continued_sign_in import ContinuedSignIn

_ALGORITHM = "HS256"
#: 発行者と宛先。別のアプリや環境のトークンは鍵で落ちるが、鍵を取り違えても混ざらないように名乗る
_NAME = "wbs"
TYPE_ACCESS = "access"
CLAIM_SESSION = "rsid"


def _timestamp(moment: datetime) -> int:
    """naive な UTC をエポック秒へ（``src/shared/clock.py`` の契約）。"""
    return int(moment.replace(tzinfo=UTC).timestamp())


class JwtSessionTokens(SessionTokens):
    def __init__(self, *, signing_key: str, access_lifetime: timedelta, carry: timedelta) -> None:
        self._key = signing_key
        self._access_lifetime = access_lifetime
        #: 期限切れのトークンから続けるログインを読む長さ（ADR-0071。Cookie を残す長さと同じ）
        self._carry = carry

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

    def continuation_of(self, token: str, *, now: datetime) -> ContinuedSignIn | None:
        claims = self._decode(token, TYPE_ACCESS, now - self._carry)
        if claims is None:
            return None
        return ContinuedSignIn(user_id=int(claims["sub"]), session_id=str(claims[CLAIM_SESSION]))

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
