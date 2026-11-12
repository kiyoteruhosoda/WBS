"""A "stop this session" notice from the IdP (OpenID Connect Back-Channel Logout 1.0).

Verifying the ``logout_token``'s **signature, issuer, audience and expiry** belongs to the infrastructure layer
(it is a JWT matter). This checks **the other 4 things**, all explicitly required
by the spec (§2.6).

- ``events`` contains the back-channel logout event
  — a JWT without it is not a "logout notice"
- ``nonce`` is **absent** — a token with it is an ID token, and accepting
  it would let anyone **trigger a logout just by sending back an ID token they hold**
- either ``sub`` or ``sid`` is present — with neither, there is no telling whom to stop
- ``jti`` is present — the key for rejecting replays (a resend of the same notice carries the same ``jti``)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity

#: Event name for back-channel logout (OpenID Connect Back-Channel Logout 1.0 §2.4).
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class InvalidLogoutTokenError(AuthenticationError):
    """The ``logout_token`` does not form a valid "logout notice".

    ⚠ **Do not return the reason to the sender.** This endpoint can be hit unauthenticated, so revealing
    how far it got would give clues for finding a form that passes.
    """


@dataclass(frozen=True)
class LogoutNotice:
    """A notice that passed verification. ``jti`` is the delivery identity and does not change on resend."""

    jti: str
    identity: FederatedIdentity | None
    session_id: str | None

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any], *, issuer: str) -> LogoutNotice:
        """Build from verified claims. Raises if it does not form a valid notice."""
        _ensure_logout_event(claims)
        _ensure_not_an_id_token(claims)
        jti = _text(claims.get("jti"))
        if not jti:
            raise InvalidLogoutTokenError("logout_token has no jti")
        subject = _text(claims.get("sub"))
        session_id = _text(claims.get("sid"))
        if not subject and not session_id:
            # With neither, there is no telling "whose" sign-in or "which" sign-in to stop.
            raise InvalidLogoutTokenError("logout_token has neither sub nor sid")
        return cls(
            jti=jti,
            identity=FederatedIdentity(issuer=issuer, subject=subject) if subject else None,
            session_id=session_id or None,
        )

    @property
    def scope(self) -> str:
        """For the record: "how much this notice stops". If there is ``sid``, only that one sign-in."""
        return "session" if self.session_id else "subject"


def _ensure_logout_event(claims: Mapping[str, Any]) -> None:
    events = claims.get("events")
    if not isinstance(events, Mapping) or LOGOUT_EVENT not in events:
        raise InvalidLogoutTokenError("logout_token does not carry the logout event")


def _ensure_not_an_id_token(claims: Mapping[str, Any]) -> None:
    """Do not accept anything carrying ``nonce`` (the spec says MUST NOT).

    ID tokens and logout tokens share signing key, issuer and audience, so **this one point** alone
    tells them apart. Dropping it would let anyone kill another person's session just by sending back
    an ID token they legitimately received.
    """
    if "nonce" in claims:
        raise InvalidLogoutTokenError("a logout_token must not carry a nonce")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["LOGOUT_EVENT", "InvalidLogoutTokenError", "LogoutNotice"]
