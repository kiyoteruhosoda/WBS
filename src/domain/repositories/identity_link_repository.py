"""Access to identity links (``federated_identities``) as rows.

For the sign-in flow, adding via ``UserAccountRepository`` is enough, but periodic reconciliation
**enumerates everything per issuer and removes single rows**, so it gets its own interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.identity_link import IdentityLink


class IdentityLinkRepository(ABC):
    @abstractmethod
    def list_for_issuer(self, issuer: str) -> list[IdentityLink]:
        """Return all rows linked with that issuer.

        ⚠ **The issuer spelling must be identical to what sign-in wrote.** If it is off
        by one character, nothing matches and the run ends as "no problems" without checking anything
        (``FederatedIdentity`` normalizes the spelling).
        """

    @abstractmethod
    def unlink(self, link_id: int) -> None:
        """Remove the row. The user itself is not deleted."""


__all__ = ["IdentityLinkRepository"]
