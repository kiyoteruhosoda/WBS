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
        # ⚠ **「引いて、無ければ足す」では足りない。** 同じ通知が同時に 2 本届くと、
        #   どちらも「無い」と読んでから両方が足しに行く。一意制約で決着させ、
        #   負けた側を「既に受けている」として扱う。
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
        """試験と調査のための確認口（ポートには載せない）。"""
        stmt = select(BackchannelLogoutDeliveryModel).where(
            BackchannelLogoutDeliveryModel.jti == jti
        )
        return self._session.scalars(stmt).first() is not None
