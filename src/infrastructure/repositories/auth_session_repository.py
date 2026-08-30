from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.auth_session import AuthSession, hash_session_token
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.infrastructure.database.models import AuthSessionModel


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

    @staticmethod
    def _to_entity(model: AuthSessionModel) -> AuthSession:
        return AuthSession(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            issued_at=model.issued_at,
            expires_at=model.expires_at,
            last_seen_at=model.last_seen_at,
        )
