"""One row linking a user and a person on the IdP (``federated_identities``).

``UserAccount.identities`` lists "the links the person has", but cannot point at **the row itself**
(it has no id). Periodic reconciliation "removes this one row", so it needs a form that can point at rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.federated_identity import FederatedIdentity


@dataclass(frozen=True)
class IdentityLink:
    id: int
    user_id: int
    identity: FederatedIdentity

    @property
    def issuer(self) -> str:
        return self.identity.issuer

    @property
    def subject(self) -> str:
        return self.identity.subject


__all__ = ["IdentityLink"]
