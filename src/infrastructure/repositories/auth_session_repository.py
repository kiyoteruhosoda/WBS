from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.auth_session import AuthSession, hash_session_token
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.infrastructure.database.models import AuthSessionModel, FederatedIdentityModel


class SqlAlchemyAuthSessionRepository(AuthSessionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, auth_session: AuthSession) -> AuthSession:
        model = AuthSessionModel(
            user_id=auth_session.user_id,
            token_hash=auth_session.token_hash,
            issued_at=auth_session.issued_at,
            expires_at=auth_session.expires_at,
            last_seen_at=auth_session.last_seen_at,
            idp_session_id=auth_session.idp_session_id,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        auth_session.id = model.id
        return auth_session

    def find_by_token(self, token: str) -> AuthSession | None:
        # 生のトークンでは引かない。DB にあるのはハッシュだけ。
        stmt = select(AuthSessionModel).where(
            AuthSessionModel.token_hash == hash_session_token(token)
        )
        model = self._session.scalars(stmt).first()
        return None if model is None else self._to_entity(model)

    def update(self, auth_session: AuthSession) -> None:
        model = self._session.get(AuthSessionModel, auth_session.id)
        if model is None:
            return
        model.last_seen_at = auth_session.last_seen_at
        model.expires_at = auth_session.expires_at
        self._session.commit()

    def delete_by_token(self, token: str) -> None:
        self._session.execute(
            delete(AuthSessionModel).where(
                AuthSessionModel.token_hash == hash_session_token(token)
            )
        )
        self._session.commit()

    def delete_expired(self, now: datetime) -> int:
        result = self._session.execute(
            delete(AuthSessionModel).where(AuthSessionModel.expires_at < now)
        )
        self._session.commit()
        return result.rowcount or 0

    def delete_for_identity(
        self, identity: FederatedIdentity, *, idp_session_id: str | None = None
    ) -> int:
        # 結び付き（``federated_identities``）から利用者を引き、その人のセッションを消す。
        # ⚠ **利用者の行には触らない。** 止めたのは IdP で、この口座の持ち主ではない。
        user_ids = select(FederatedIdentityModel.user_id).where(
            FederatedIdentityModel.issuer == identity.issuer,
            FederatedIdentityModel.subject == identity.subject,
        )
        stmt = delete(AuthSessionModel).where(AuthSessionModel.user_id.in_(user_ids))
        if idp_session_id is not None:
            # ⚠ その IdP のログインから始まったセッションだけ。``sid`` を覚える前に
            #   始まったセッション（NULL）は当たらない ——ここで巻き込むと、
            #   よその端末の停止で自分のセッションまで終わる。
            stmt = stmt.where(AuthSessionModel.idp_session_id == idp_session_id)
        result = self._session.execute(stmt)
        self._session.commit()
        return result.rowcount or 0

    def delete_for_idp_session(self, *, issuer: str, idp_session_id: str) -> int:
        user_ids = select(FederatedIdentityModel.user_id).where(
            FederatedIdentityModel.issuer == issuer
        )
        result = self._session.execute(
            delete(AuthSessionModel).where(
                AuthSessionModel.idp_session_id == idp_session_id,
                AuthSessionModel.user_id.in_(user_ids),
            )
        )
        self._session.commit()
        return result.rowcount or 0

    @staticmethod
    def _to_entity(model: AuthSessionModel) -> AuthSession:
        return AuthSession(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            issued_at=model.issued_at,
            expires_at=model.expires_at,
            last_seen_at=model.last_seen_at,
            idp_session_id=model.idp_session_id,
        )
