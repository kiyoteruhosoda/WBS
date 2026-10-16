from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
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
            started_at=model.started_at,
            ended_at=model.ended_at,
            task_id=model.task_id,
        )

    def add(self, receipt: AutoTimeEntryReceipt) -> None:
        self._session.add(
            AutoTimeEntryReceiptModel(
                user_id=receipt.user_id,
                client_ref=receipt.client_ref,
                mode=receipt.mode.value,
                received_at=receipt.received_at,
                started_at=receipt.started_at,
                ended_at=receipt.ended_at,
                task_id=receipt.task_id,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("this client_ref has already been received") from exc

    def extend(self, user_id: int, client_ref: str, ended_at: datetime) -> None:
        self._session.execute(
            update(AutoTimeEntryReceiptModel)
            .where(
                AutoTimeEntryReceiptModel.user_id == user_id,
                AutoTimeEntryReceiptModel.client_ref == client_ref,
            )
            .values(ended_at=ended_at)
        )
        self._session.flush()
