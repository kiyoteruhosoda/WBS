from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.repositories.logout_delivery_repository import LogoutDeliveryRepository
from src.infrastructure.database.models import BackchannelLogoutDeliveryModel


class SqlAlchemyLogoutDeliveryRepository(LogoutDeliveryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, *, jti: str, now: datetime) -> bool:
        # ⚠ **"Look up, add if missing" is not enough.** If the same notification arrives twice at once,
        #   both read "missing" and then both try to add. Let the unique constraint decide, and
        #   treat the loser as "already received".
        self._session.add(BackchannelLogoutDeliveryModel(jti=jti, received_at=now))
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            return False
        return True

    def delete_expired(self, now: datetime) -> int:
        result = self._session.execute(
            delete(BackchannelLogoutDeliveryModel).where(
                BackchannelLogoutDeliveryModel.received_at < now
            )
        )
        self._session.commit()
        return result.rowcount or 0

    def has(self, jti: str) -> bool:
        """Lookup for tests and investigation (not part of the port)."""
        stmt = select(BackchannelLogoutDeliveryModel).where(
            BackchannelLogoutDeliveryModel.jti == jti
        )
        return self._session.scalars(stmt).first() is not None
