"""利用者と IdP 上の本人を結ぶ 1 行（``federated_identities``）。

``UserAccount.identities`` は「その人が持つ結び付き」の一覧だが、**行そのもの**を
指せない（id を持たない）。定期照合は「この 1 行を外す」を行うので、行を指せる形が要る。
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
