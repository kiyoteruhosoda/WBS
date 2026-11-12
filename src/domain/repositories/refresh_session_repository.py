from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.refresh_session import RefreshSession
from src.domain.value_objects.federated_identity import FederatedIdentity


class RefreshSessionRepository(ABC):
    @abstractmethod
    def add(self, session: RefreshSession) -> None: ...
    @abstractmethod
    def find(self, session_id: str) -> RefreshSession | None: ...
    @abstractmethod
    def delete(self, session_id: str) -> None: ...
    @abstractmethod
    def delete_expired(self, now: datetime) -> int: ...

    @abstractmethod
    def extend(self, session_id: str, *, idp_session_id: str | None, expires_at: datetime) -> bool:
        """Extend a continued sign-in and re-point it at the IdP-side sign-in (ADR-0071). False if there is no row."""

    @abstractmethod
    def delete_for_identity(
        self, identity: FederatedIdentity, *, idp_session_id: str | None = None
    ) -> int:
        """Look up by the person on the IdP and end their sign-ins in this app (returns the number deleted).

        Passing ``idp_session_id`` ends **only the ones that started from that IdP sign-in**.
        Without it, all of that person's sign-ins are ended.

        ⚠ **This does not verify that the person is who they claim to be.** The caller (logout
        notice, periodic reconciliation) verifies the IdP signature before calling.
        """

    @abstractmethod
    def delete_for_idp_session(self, *, issuer: str, idp_session_id: str) -> int:
        """For notices without ``sub``: look up by ``sid`` alone and end the sign-ins.

        The spec only requires either ``sub`` or ``sid`` (§2.6), so a notice
        carrying only ``sid`` is still a valid recipient.
        """
