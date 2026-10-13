from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.auto_time_entry_receipt import AutoTimeEntryReceipt
from src.domain.exceptions import ConflictError
from src.domain.repositories.auto_time_entry_receipt_repository import (
    AutoTimeEntryReceiptRepository,
)
from src.domain.value_objects.auto_entry_mode import AutoEntryMode
from src.infrastructure.database.models import AutoTimeEntryReceiptModel


class SqlAlchemyAutoTimeEntryReceiptRepository(AutoTimeEntryReceiptRepository):
    """⚠ ``add`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, user_id: int, client_ref: str) -> AutoTimeEntryReceipt | None:
        model = self._session.scalar(
            select(AutoTimeEntryReceiptModel).where(
                AutoTimeEntryReceiptModel.user_id == user_id,
                AutoTimeEntryReceiptModel.client_ref == client_ref,
            )
        )
        if model is None:
            return None
        return AutoTimeEntryReceipt(
            user_id=model.user_id,
            client_ref=model.client_ref,
            mode=AutoEntryMode(model.mode),
            received_at=model.received_at,
        )

    def add(self, receipt: AutoTimeEntryReceipt) -> None:
        self._session.add(
            AutoTimeEntryReceiptModel(
                user_id=receipt.user_id,
                client_ref=receipt.client_ref,
                mode=receipt.mode.value,
                received_at=receipt.received_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("this client_ref has already been received") from exc
