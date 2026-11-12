from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

from src.domain.entities.refresh_session import RefreshSession
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.infrastructure.database.models import FederatedIdentityModel, RefreshSessionModel


class SqlAlchemyRefreshSessionRepository(RefreshSessionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, refresh_session: RefreshSession) -> None:
        self._session.add(
            RefreshSessionModel(
                id=refresh_session.id,
                user_id=refresh_session.user_id,
                expires_at=refresh_session.expires_at,
                created_at=refresh_session.created_at,
                idp_session_id=refresh_session.idp_session_id,
            )
        )
        self._session.commit()

    def find(self, session_id: str) -> RefreshSession | None:
        model = self._session.scalars(
            select(RefreshSessionModel).where(RefreshSessionModel.id == session_id)
        ).first()
        return None if model is None else self._to_entity(model)

    def delete(self, session_id: str) -> None:
        self._session.execute(delete(RefreshSessionModel).where(RefreshSessionModel.id == session_id))
        self._session.commit()

    def delete_expired(self, now: datetime) -> int:
        result = self._execute(delete(RefreshSessionModel).where(RefreshSessionModel.expires_at < now))
        self._session.commit()
        return result.rowcount or 0

    def extend(self, session_id: str, *, idp_session_id: str | None, expires_at: datetime) -> bool:
        result = self._execute(
            update(RefreshSessionModel)
            .where(RefreshSessionModel.id == session_id)
            .values(idp_session_id=idp_session_id, expires_at=expires_at),
            execution_options={"synchronize_session": False},
        )
        self._session.commit()
        return result.rowcount == 1

    def delete_for_identity(
        self, identity: FederatedIdentity, *, idp_session_id: str | None = None
    ) -> int:
        # Look up the user via the link (``federated_identities``) and delete that person's logins.
        # ⚠ **Do not touch the user row.** It was the IdP that stopped the session, not the account owner.
        user_ids = select(FederatedIdentityModel.user_id).where(
            FederatedIdentityModel.issuer == identity.issuer,
            FederatedIdentityModel.subject == identity.subject,
        )
        stmt = delete(RefreshSessionModel).where(RefreshSessionModel.user_id.in_(user_ids))
        if idp_session_id is not None:
            # ⚠ Only logins that started from that IdP login. Logins without a ``sid`` (NULL) do not match
            #   -- including them would end your own login when another device is signed out.
            stmt = stmt.where(RefreshSessionModel.idp_session_id == idp_session_id)
        result = self._execute(stmt)
        self._session.commit()
        return result.rowcount or 0

    def delete_for_idp_session(self, *, issuer: str, idp_session_id: str) -> int:
        user_ids = select(FederatedIdentityModel.user_id).where(
            FederatedIdentityModel.issuer == issuer
        )
        result = self._execute(
            delete(RefreshSessionModel).where(
                RefreshSessionModel.idp_session_id == idp_session_id,
                RefreshSessionModel.user_id.in_(user_ids),
            )
        )
        self._session.commit()
        return result.rowcount or 0

    def _execute(self, statement: Any, **kwargs: Any) -> CursorResult[Any]:
        return cast("CursorResult[Any]", self._session.execute(statement, **kwargs))

    @staticmethod
    def _to_entity(model: RefreshSessionModel) -> RefreshSession:
        return RefreshSession(
            id=model.id,
            user_id=model.user_id,
            expires_at=model.expires_at,
            created_at=model.created_at,
            idp_session_id=model.idp_session_id,
        )
