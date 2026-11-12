"""Create and read the tokens this app issues itself, as JWT (HS256) (ADR-0069, ADR-0071).

Only access tokens are issued. ⚠ **Always check ``type`` when reading.** So that refresh tokens and
logout tickets (``refresh`` / ``logout``) issued in the past cannot call the API even if someone still holds them.

Expiry is compared with ``now`` (the library gets no clock; the single time source is ``src/shared/clock.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.session_tokens import AccessTokenContents, SessionTokens
from src.domain.value_objects.continued_sign_in import ContinuedSignIn

_ALGORITHM = "HS256"
#: Issuer and audience. Tokens of other apps/environments fail on the key anyway, but naming them keeps them apart even if keys get mixed up
_NAME = "wbs"
TYPE_ACCESS = "access"
CLAIM_SESSION = "rsid"


def _timestamp(moment: datetime) -> int:
    """Naive UTC to epoch seconds (the ``src/shared/clock.py`` contract)."""
    return int(moment.replace(tzinfo=UTC).timestamp())


class JwtSessionTokens(SessionTokens):
    def __init__(self, *, signing_key: str, access_lifetime: timedelta, carry: timedelta) -> None:
        self._key = signing_key
        self._access_lifetime = access_lifetime
        #: How long a login may be continued from an expired token (ADR-0071; same as how long the cookie is kept)
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
