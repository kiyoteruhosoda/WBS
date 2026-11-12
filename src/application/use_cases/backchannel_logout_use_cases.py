"""Receive stop notifications from the IdP (OpenID Connect Back-Channel Logout 1.0).

This endpoint is **not called from the user's browser**. The IdP's server calls it directly
server-to-server, and the signature of the received ``logout_token`` is the only proof of the caller.

It does one thing: **delete the login records (``refresh_sessions``) that match the target**. The access token expires with its lifetime (5 minutes),
and when the frontend asks the IdP again the IdP answers "not signed in", so access ends within that lifetime at the latest (ADR-0071).

⚠ **Do not touch the user itself (``users.is_active``).** It was the IdP that stopped them,
not an admin of this app. Once restored at the IdP, they can sign in again as is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.ports.identity_provider import IdentityProvider
from src.domain.repositories.logout_delivery_repository import LogoutDeliveryRepository
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.value_objects.logout_notice import LogoutNotice

logger = logging.getLogger(__name__)

#: Default retention of delivery records. Callers pass the refresh token lifetime. **Anything longer than the login record lifetime is enough**
#: — after that, any record a replay could delete has already expired on its own.
DEFAULT_DELIVERY_RETENTION = timedelta(days=14)


@dataclass(frozen=True)
class ReceivedLogout:
    """Result of receiving (counts for logging and tests)."""

    notice: LogoutNotice
    #: Whether this is the first delivery of the notice. ⚠ ``False`` for a replay, in which case no sessions were deleted.
    first_delivery: bool
    ended_sessions: int


class ReceiveBackchannelLogout:
    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        sessions: RefreshSessionRepository,
        deliveries: LogoutDeliveryRepository,
        delivery_retention: timedelta = DEFAULT_DELIVERY_RETENTION,
    ) -> None:
        self._idp = identity_provider
        self._sessions = sessions
        self._deliveries = deliveries
        self._delivery_retention = delivery_retention

    def execute(self, *, logout_token: str, now: datetime) -> ReceivedLogout:
        claims = self._idp.verify_logout_token(logout_token)
        notice = LogoutNotice.from_claims(claims, issuer=self._idp.federated_issuer)
        self._deliveries.delete_expired(now - self._delivery_retention)
        # ⚠ **Do not delete on a replay.** Senders reuse the same ``jti`` for a resend, so letting it
        #   through would make a replay of an old notice delete **sessions created after signing in again**.
        if not self._deliveries.record(jti=notice.jti, now=now):
            logger.info(
                "Ignored a replayed logout notice",
                extra={"event": "auth.oidc.logout_replayed", "scope": notice.scope},
            )
            return ReceivedLogout(notice=notice, first_delivery=False, ended_sessions=0)
        ended = self._end_sessions(notice)
        logger.info(
            "Ended sessions on a logout notice from the IdP",
            extra={
                "event": "auth.oidc.logout_received",
                "scope": notice.scope,
                "ended_sessions": ended,
            },
        )
        return ReceivedLogout(notice=notice, first_delivery=True, ended_sessions=ended)

    def _end_sessions(self, notice: LogoutNotice) -> int:
        if notice.identity is not None:
            return self._sessions.delete_for_identity(
                notice.identity, idp_session_id=notice.session_id
            )
        # A notice with only ``sid`` and no ``sub`` (allowed by the spec). Look it up paired with the issuer.
        assert notice.session_id is not None  # LogoutNotice guarantees one of the two
        return self._sessions.delete_for_idp_session(
            issuer=self._idp.federated_issuer, idp_session_id=notice.session_id
        )


__all__ = ["DEFAULT_DELIVERY_RETENTION", "ReceiveBackchannelLogout", "ReceivedLogout"]
