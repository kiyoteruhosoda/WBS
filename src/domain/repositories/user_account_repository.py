from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.user_account import UserAccount
from src.domain.value_objects.federated_identity import FederatedIdentity


class UserAccountRepository(ABC):
    @abstractmethod
    def find_by_id(self, user_id: int) -> UserAccount | None: ...
    @abstractmethod
    def find_by_identity(self, identity: FederatedIdentity) -> UserAccount | None: ...
    @abstractmethod
    def find_by_email(self, email: str) -> UserAccount | None: ...
    @abstractmethod
    def save(self, user: UserAccount) -> UserAccount: ...
