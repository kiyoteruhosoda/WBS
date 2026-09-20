"""結び付き（``federated_identities``）を行として扱う口。

ログインの筋道は ``UserAccountRepository`` 側で足すだけで足りるが、定期照合は
**発行者ごとに全部を数え上げ、1 行を外す**ので、別の口として立てる。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.identity_link import IdentityLink


class IdentityLinkRepository(ABC):
    @abstractmethod
    def list_for_issuer(self, issuer: str) -> list[IdentityLink]:
        """その発行者で結ばれている行をすべて返す。

        ⚠ **発行者の綴りはログインで書いたものと同じでなければならない。** 1 文字
        ずれると 0 件になり、何も確かめないまま「異常なし」で終わる
        （``FederatedIdentity`` が綴りを揃える）。
        """

    @abstractmethod
    def unlink(self, link_id: int) -> None:
        """行を外す。利用者そのものは消さない。"""


__all__ = ["IdentityLinkRepository"]
