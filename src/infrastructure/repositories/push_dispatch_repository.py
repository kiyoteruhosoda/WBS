from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.repositories.push_dispatch_repository import PushDispatchRepository
from src.domain.value_objects.push_kind import PushKind
from src.infrastructure.database.models import PushDispatchModel


class SqlAlchemyPushDispatchRepository(PushDispatchRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(self, user_id: int, kind: PushKind, key: str, at: datetime) -> bool:
        # ⚠ ここで確定する（ほかのプロセスに「取った」を見せてから送る）。手前に未確定の
        #   書き込みがあれば一緒に確定する —— 送る係は記録の前に何も書かない。
        self._session.add(
            PushDispatchModel(user_id=user_id, kind=kind.value, notice_key=key, sent_at=at)
        )
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            return False
        return True

    def purge_before(self, at: datetime) -> None:
        self._session.execute(delete(PushDispatchModel).where(PushDispatchModel.sent_at < at))
        self._session.commit()
