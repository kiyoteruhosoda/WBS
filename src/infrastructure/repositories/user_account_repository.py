from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.user_account import UserAccount
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.infrastructure.database.models import FederatedIdentityModel, UserModel
from src.shared.clock import utcnow


class SqlAlchemyUserAccountRepository(UserAccountRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, user_id: int) -> UserAccount | None:
        model = self._session.get(UserModel, user_id)
        return None if model is None else self._to_entity(model)

    def find_by_identity(self, identity: FederatedIdentity) -> UserAccount | None:
        stmt = select(UserModel).join(
            FederatedIdentityModel, FederatedIdentityModel.user_id == UserModel.id
        ).where(
            FederatedIdentityModel.issuer == identity.issuer,
            FederatedIdentityModel.subject == identity.subject,
        )
        model = self._session.scalars(stmt).first()
        return None if model is None else self._to_entity(model)

    def find_by_email(self, email: str) -> UserAccount | None:
        model = self._session.scalars(select(UserModel).where(UserModel.email == email)).first()
        return None if model is None else self._to_entity(model)

    def save(self, user: UserAccount) -> UserAccount:
        if user.id is None:
            model = UserModel(
                email=user.email,
                display_name=user.display_name,
                timezone=user.timezone,
                language=user.language,
                is_active=user.is_active,
            )
            self._session.add(model)
            self._session.flush()
        else:
            model = self._session.get(UserModel, user.id)
            if model is None:
                raise ValueError(f"User {user.id} not found")
            model.email = user.email
            model.display_name = user.display_name
            model.timezone = user.timezone
            model.language = user.language
            model.is_active = user.is_active
            model.updated_at = utcnow()
        self._sync_identities(model.id, user.identities)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def _sync_identities(self, user_id: int, identities: list[FederatedIdentity]) -> None:
        """エンティティ側で増えた紐付けだけを足す（既存は消さない）。

        紐付けの削除は管理操作としてのみ行う想定なので、ログインの筋道からは
        取り外さない。「IdP が sub を返さなくなった＝解除」と読むと、IdP 側の
        一時的な不調で全員の紐付けが飛ぶ。
        """
        stmt = select(FederatedIdentityModel).where(FederatedIdentityModel.user_id == user_id)
        known = {(m.issuer, m.subject) for m in self._session.scalars(stmt)}
        for identity in identities:
            if (identity.issuer, identity.subject) not in known:
                self._session.add(
                    FederatedIdentityModel(
                        user_id=user_id, issuer=identity.issuer, subject=identity.subject
                    )
                )
        self._session.flush()

    def _to_entity(self, model: UserModel) -> UserAccount:
        stmt = select(FederatedIdentityModel).where(FederatedIdentityModel.user_id == model.id)
        identities = [
            FederatedIdentity(issuer=m.issuer, subject=m.subject)
            for m in self._session.scalars(stmt)
        ]
        return UserAccount(
            id=model.id,
            email=model.email,
            display_name=model.display_name,
            timezone=model.timezone,
            language=model.language,
            is_active=model.is_active,
            identities=identities,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
